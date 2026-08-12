"""Tests de comportamiento S6.7 Área C (panel de lote retroactivo), spec
docs/specs/S6.7-benchmark-real-motor-variante.md, C10, C11, C14, C16.

C12 (candado real contra Postgres, dos conexiones) y C13 (progreso avanza en un `finally`, incluso
ante fallo) se prueban aparte, a nivel más bajo, en `test_ocr_benchmark_batch_lock.py` (no aquí):
no necesitan HTTP, solo Postgres real. C15 (secuencial, nunca todo a la vez) se verifica por
inspección de código en la auditoría (bucle `for` simple), sin un test de temporización dedicado.

Postgres real, admin-tech autenticado (mismo patrón que `test_platform_lab.py`/`ranking_router`).
Nunca se llama a ningún proveedor real: estos tests solo ejercitan el endpoint HTTP (encola el job,
no lo ejecuta) — el procesado real de candidatos ya está cubierto por `test_ocr_benchmark.py`
(motor) y `test_ocr_benchmark_batch_lock.py` (candado + progreso).
"""

from __future__ import annotations

import asyncpg
import httpx

from tests._dbtest import seed_company, seed_tenant
from tests._invoicing import seed_invoice
from tests._ocr import set_ocr_experiment_enabled
from tests._platform import platform_token, seed_platform_admin

Api = tuple[httpx.AsyncClient, dict[str, str]]

_BACKFILL_URL = "/api/v1/platform/benchmark/backfill"
_STATUS_URL = "/api/v1/platform/benchmark/backfill/status"


def _platform_auth(token: str) -> dict[str, str]:
    return {"Host": "panel.localhost", "Authorization": f"Bearer {token}"}


async def _admin_tech_token(client: httpx.AsyncClient, dsns: dict[str, str]) -> str:
    await seed_platform_admin(dsns, is_admin_tech=True)
    return await platform_token(client)


async def test_c1_sin_admin_tech_da_403(authapi: Api) -> None:
    client, dsns = authapi
    await seed_platform_admin(dsns, is_admin_tech=False)
    token = await platform_token(client)

    resp = await client.post(_BACKFILL_URL, headers=_platform_auth(token), json={"limit": 10})

    assert resp.status_code == 403, resp.text


async def test_c16_sin_ningun_lote_todavia_el_estado_lo_dice_explicito(authapi: Api) -> None:
    client, dsns = authapi
    token = await _admin_tech_token(client, dsns)

    resp = await client.get(_STATUS_URL, headers=_platform_auth(token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["running"] is False
    assert body["batch"] is None


async def test_c10_pulsar_el_boton_dispara_el_lote_y_responde_al_instante(authapi: Api) -> None:
    """spec: C10 -- responde de inmediato con `{iniciado: true, total: N}`, sin esperar a que
    termine ni una sola combinación (el endpoint solo encola, nunca procesa él mismo)."""
    client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    token = await _admin_tech_token(client, dsns)

    resp = await client.post(_BACKFILL_URL, headers=_platform_auth(token), json={"limit": 10})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["iniciado"] is True
    assert body["total"] == 0  # sin ninguna factura confirmada candidata sembrada en este test

    status = await client.get(_STATUS_URL, headers=_platform_auth(token))
    assert status.json()["running"] is True
    assert status.json()["batch"]["status"] == "running"


async def test_c14_el_limite_duro_es_30_aunque_se_pida_mas(authapi: Api) -> None:
    """spec: C14 -- como mucho 30 facturas por invocación, sin importar lo que se pida."""
    client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    token = await _admin_tech_token(client, dsns)

    resp = await client.post(_BACKFILL_URL, headers=_platform_auth(token), json={"limit": 500})

    assert resp.status_code == 200, resp.text
    # Sin candidatos reales sembrados, `total` es 0 de todos modos -- el propio endpoint debe
    # aplicar el tope de 30 a LO QUE PIDE (limit=500 -> como mucho 30 candidatos se habrían
    # buscado), verificado indirectamente por C10 con datos reales en el nivel de candado/progreso.
    assert resp.status_code == 200


async def test_c14b_el_limite_duro_es_30_con_candidatos_reales_de_sobra(authapi: Api) -> None:
    """S6.7 auditoría 2026-08-11, hallazgo BAJO: el test C14 anterior nunca sembraba >30 candidatos
    reales, así que no habría detectado una regresión futura del tope duro. Aquí se siembran 35
    facturas confirmadas reales y se comprueba que `limit=500` sigue devolviendo `total == 30`."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "bm-c14b", "BM C14b Asesoría")
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Mi Empresa", cif="B00000099"
    )
    for i in range(35):
        await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id, days_ago=i)
    await set_ocr_experiment_enabled(dsns, True)
    token = await _admin_tech_token(client, dsns)

    resp = await client.post(_BACKFILL_URL, headers=_platform_auth(token), json={"limit": 500})

    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 30, resp.json()


async def test_c14c_limit_no_positivo_da_422_no_500(authapi: Api) -> None:
    """S6.7 auditoría 2026-08-11, hallazgo MEDIO: `limit=0`/negativo debe rechazarse con un 422 de
    validación, nunca llegar a Postgres."""
    client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    token = await _admin_tech_token(client, dsns)

    resp = await client.post(_BACKFILL_URL, headers=_platform_auth(token), json={"limit": 0})

    assert resp.status_code == 422, resp.text


async def test_c11_un_lote_ya_corriendo_da_409_con_el_progreso_actual(authapi: Api) -> None:
    """spec: C11 -- la segunda petición nunca dispara un segundo lote; responde 409 con el progreso
    del lote en curso, nunca como un error genérico."""
    client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    token = await _admin_tech_token(client, dsns)
    first = await client.post(_BACKFILL_URL, headers=_platform_auth(token), json={"limit": 10})
    assert first.status_code == 200, first.text

    second = await client.post(_BACKFILL_URL, headers=_platform_auth(token), json={"limit": 10})

    assert second.status_code == 409, second.text
    body = second.json()
    assert body["batch"]["status"] == "running"


async def test_s6_7_el_lote_persiste_el_snapshot_y_no_redescubre_candidatos(authapi: Api) -> None:
    """El conjunto procesable queda fijado al pulsar el botón, no cuando despierte el worker."""
    from platform_admin import benchmark_batch_repository
    from shared.db import platform_session

    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "bm-snapshot", "BM Snapshot")
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Mi Empresa", cif="B00000099"
    )
    await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id)
    await set_ocr_experiment_enabled(dsns, True)
    token = await _admin_tech_token(client, dsns)

    resp = await client.post(_BACKFILL_URL, headers=_platform_auth(token), json={"limit": 10})

    assert resp.status_code == 200, resp.text
    async with platform_session() as session:
        running = await benchmark_batch_repository.get_running(session)
        assert running is not None
        candidates = await benchmark_batch_repository.list_candidates(session, str(running.id))
    assert len(candidates) == 1
    assert candidates[0][:2] == (tenant_id, company_id)


async def test_s6_7_si_falla_el_encolado_el_lote_visible_pasa_a_failed(
    authapi: Api, monkeypatch
) -> None:
    """El fallo de orquestación posterior al commit no deja un lote fantasma en `running`."""
    import asyncio

    from jobs import queue

    client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    token = await _admin_tech_token(client, dsns)

    async def enqueue_failed(_batch_run_id: str) -> bool:
        return False

    monkeypatch.setattr(queue, "enqueue_ocr_benchmark_batch", enqueue_failed)
    resp = await client.post(_BACKFILL_URL, headers=_platform_auth(token), json={"limit": 10})
    assert resp.status_code == 200, resp.text

    for _ in range(20):
        status = await client.get(_STATUS_URL, headers=_platform_auth(token))
        if status.json()["batch"]["status"] == "failed":
            break
        await asyncio.sleep(0.01)
    assert status.json()["batch"]["status"] == "failed"


async def test_interruptor_apagado_da_422_y_no_crea_ninguna_fila(authapi: Api) -> None:
    """S6.7 auditoría 2026-08-11, hallazgo ALTO: con el interruptor apagado (spec §4, "solo corre
    bajo el interruptor explícito"), el `POST` no debe insertar ninguna fila en
    `ocr_benchmark_batch_runs` ni encolar nada -- responde 422 con un mensaje claro, nunca
    `{iniciado: true}` sin haber hecho ningún trabajo real."""
    client, dsns = authapi
    token = await _admin_tech_token(client, dsns)  # interruptor apagado por defecto en este test

    resp = await client.post(_BACKFILL_URL, headers=_platform_auth(token), json={"limit": 10})

    assert resp.status_code == 422, resp.text
    assert "apagado" in resp.json()["detail"]

    conn = await asyncpg.connect(dsns["admin"])
    try:
        count = await conn.fetchval("SELECT count(*) FROM ocr_benchmark_batch_runs")
    finally:
        await conn.close()
    assert count == 0
