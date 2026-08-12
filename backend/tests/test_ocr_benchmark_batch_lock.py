"""Tests de comportamiento S6.7 Área C (candado real + progreso), spec
docs/specs/S6.7-benchmark-real-motor-variante.md, C12, C13.

Postgres/MinIO reales. C12 prueba el mecanismo de `pg_advisory_lock` en sí, con dos conexiones
reales (no simulado) contra la MISMA clave que usa el código de producción -- defensa en
profundidad, la última línea de defensa aunque el 409 de `test_platform_benchmark_backfill.py`
(C11) ya debería evitar la carrera en el 99% de los casos. C13 prueba que un documento fallido
(fichero borrado de MinIO) avanza igual el contador `completed`, vía un `finally`, sin dejar la
barra de progreso clavada.
"""

from __future__ import annotations

import asyncpg

from invoice_intake import storage
from jobs.ocr_benchmark_batch import BATCH_LOCK_KEY, run_benchmark_batch
from tests._invoicing import auth, confirm_body, confirm_url, seed_confirmable
from tests._ocr import make_extractor, set_ocr_experiment_enabled

Api = tuple[object, dict[str, str]]


async def _seed_batch_run(dsns: dict[str, str], *, total: int) -> str:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow(
            "INSERT INTO ocr_benchmark_batch_runs (status, total) VALUES ('running', $1) "
            "RETURNING id",
            total,
        )
        return str(row["id"])
    finally:
        await conn.close()


async def _fetch_batch_run(dsns: dict[str, str], *, batch_run_id: str) -> dict:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow(
            "SELECT * FROM ocr_benchmark_batch_runs WHERE id = $1", batch_run_id
        )
        return dict(row)
    finally:
        await conn.close()


async def test_c12_el_candado_real_protege_aunque_el_409_falle(authapi: Api) -> None:
    """spec: C12 -- dos conexiones reales tomando el mismo `pg_advisory_lock`, no simulado: solo una
    lo consigue mientras la otra lo mantiene; se libera y la segunda pasa a poder tomarlo."""
    _client, dsns = authapi
    conn1 = await asyncpg.connect(dsns["admin"])
    conn2 = await asyncpg.connect(dsns["admin"])
    try:
        await conn1.execute("SELECT pg_advisory_lock($1)", BATCH_LOCK_KEY)

        got_while_held = await conn2.fetchval("SELECT pg_try_advisory_lock($1)", BATCH_LOCK_KEY)
        assert got_while_held is False

        await conn1.execute("SELECT pg_advisory_unlock($1)", BATCH_LOCK_KEY)

        got_after_release = await conn2.fetchval("SELECT pg_try_advisory_lock($1)", BATCH_LOCK_KEY)
        assert got_after_release is True
        await conn2.execute("SELECT pg_advisory_unlock($1)", BATCH_LOCK_KEY)
    finally:
        await conn1.close()
        await conn2.close()


async def test_s6_7_el_arranque_atomico_solo_crea_un_lote_bajo_carrera_real(authapi: Api) -> None:
    """Dos transacciones reales no pueden pasar a la vez el antiguo get_running + insert."""
    import asyncio

    _client, dsns = authapi
    conn1 = await asyncpg.connect(dsns["admin"])
    conn2 = await asyncpg.connect(dsns["admin"])
    try:
        first, second = await asyncio.gather(
            conn1.fetchrow("SELECT * FROM start_benchmark_batch(10)"),
            conn2.fetchrow("SELECT * FROM start_benchmark_batch(10)"),
        )
        assert sorted((first["started"], second["started"])) == [False, True]
        count = await conn1.fetchval(
            "SELECT count(*) FROM ocr_benchmark_batch_runs WHERE status = 'running'"
        )
        assert count == 1
    finally:
        await conn1.close()
        await conn2.close()


async def test_c13_un_documento_fallido_tambien_avanza_completed_sin_bloquear_el_resto(
    authapi: Api,
) -> None:
    """spec: C13 -- un fichero borrado de MinIO cuenta como fallo (`failed_count` +1) y
    `completed` avanza igual (en un `finally`), sin dejar la barra clavada; el resto de la
    factura del lote se procesa con normalidad."""
    client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)

    ok = await seed_confirmable(dsns, client, slug="batch-ok", email="ok@batch-ok.es")
    resp_ok = await client.post(
        confirm_url(ok["file_id"]),
        headers=auth(ok["token"], "batch-ok.localhost"),
        json=confirm_body(),
    )
    assert resp_ok.status_code == 201, resp_ok.text

    broken = await seed_confirmable(dsns, client, slug="batch-bad", email="bad@batch-bad.es")
    resp_broken = await client.post(
        confirm_url(broken["file_id"]),
        headers=auth(broken["token"], "batch-bad.localhost"),
        json=confirm_body(),
    )
    assert resp_broken.status_code == 201, resp_broken.text
    # Simula un fichero real desaparecido de MinIO (borrado, cuota, incidente de infra) tras
    # confirmarse -- no un doble inventado, un objeto real que deja de existir.
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow(
            "SELECT storage_bucket, storage_key FROM uploaded_files WHERE id = $1",
            broken["file_id"],
        )
    finally:
        await conn.close()
    storage.remove_object(row["storage_bucket"], row["storage_key"])

    batch_run_id = await _seed_batch_run(dsns, total=2)

    await run_benchmark_batch(
        batch_run_id,
        candidates=[
            (ok["tenant_id"], ok["company_id"], ok["file_id"]),
            (broken["tenant_id"], broken["company_id"], broken["file_id"]),
        ],
        extractors=[("gemini-3-flash", make_extractor(_perfect_invoice()))],
    )

    batch = await _fetch_batch_run(dsns, batch_run_id=batch_run_id)
    assert batch["completed"] == 2, batch
    assert batch["failed_count"] == 1, batch
    assert batch["status"] == "done", batch


async def test_s6_7_un_redelivery_de_lote_cerrado_no_repite_el_trabajo_ni_el_progreso(
    authapi: Api, monkeypatch
) -> None:
    """ARQ puede repetir un mensaje tras una caída: un lote ya terminado se ignora antes de llamar
    a ningún motor, por lo que no vuelve a generar gasto ni deja completed por encima de total."""
    from jobs import ocr_benchmark_batch

    _client, dsns = authapi
    batch_run_id = await _seed_batch_run(dsns, total=1)
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "UPDATE ocr_benchmark_batch_runs SET status = 'done', completed = 1 WHERE id = $1",
            batch_run_id,
        )
    finally:
        await conn.close()

    async def must_not_run(_batch_run_id: str, _settings: object) -> None:
        raise AssertionError("un lote cerrado no debe volver a llamar a proveedores")

    monkeypatch.setattr(ocr_benchmark_batch, "_discover_and_run", must_not_run)
    await ocr_benchmark_batch.run_benchmark_batch_task({}, batch_run_id)

    batch = await _fetch_batch_run(dsns, batch_run_id=batch_run_id)
    assert batch["status"] == "done"
    assert batch["completed"] == batch["total"] == 1


async def test_s6_7_el_progreso_no_avanza_tras_cerrar_el_lote(authapi: Api) -> None:
    """La función SQL es una segunda defensa: incluso una llamada tardía no altera x/N."""
    _client, dsns = authapi
    batch_run_id = await _seed_batch_run(dsns, total=1)
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute("SELECT finish_batch_run($1, 'done')", batch_run_id)
        await conn.execute("SELECT advance_batch_run_progress($1, true)", batch_run_id)
    finally:
        await conn.close()

    batch = await _fetch_batch_run(dsns, batch_run_id=batch_run_id)
    assert batch["completed"] == 0
    assert batch["failed_count"] == 0


def _perfect_invoice():
    from tests._ocr import build_extracted

    return build_extracted()
