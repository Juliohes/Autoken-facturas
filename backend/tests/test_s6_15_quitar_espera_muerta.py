"""Tests de comportamiento de S6.15: quitar la espera muerta del OCR (backend).

spec: docs/specs/S6.15-quitar-espera-muerta-ocr.md

C1 — la comparativa experimental (S2.10) corre como tarea de fondo PROPIA, no inline dentro de
     `run_ocr`: el job principal libera su hueco del worker en cuanto el resultado está persistido.
C3 — las páginas de una factura multipágina se descargan del almacén EN PARALELO, conservando orden.
C4 — un proveedor colgado se corta y marca `ocr_failed` mucho antes que el timeout actual (8 min).

Contra Postgres/Redis/MinIO REALES (mismo estilo que `test_s6_14_captura_alta_resolucion.py`): el
worker OCR real (`jobs.ocr.run_ocr`) con un extractor doble inyectado; nunca un proveedor real.
"""

from __future__ import annotations

import time
from uuid import UUID

import httpx
import pytest

from tests._dbtest import seed_company
from tests._intake import seed_tenant_admin
from tests._ocr import (
    OWN_CIF,
    build_extracted,
    count_comparison_runs,
    fetch_extraction,
    make_comparison_extractor,
    run_ocr,
    seed_uploaded_file,
    set_ocr_experiment_enabled,
)

# pytestmark = pytest.mark.asyncio removed to allow sync tests without warnings

Api = tuple[httpx.AsyncClient, dict[str, str]]


async def _seed_pending_upload(dsns: dict[str, str], *, slug: str) -> tuple[str, str, str]:
    """Siembra tenant + admin + empresa + un fichero en `pending_ocr`. Devuelve (tenant, company,
    file)."""
    tenant_id, admin_id = await seed_tenant_admin(dsns, slug=slug, email=f"admin@{slug}.es")
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Mi Empresa", cif=OWN_CIF
    )
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=admin_id
    )
    return tenant_id, company_id, file_id


# --- C1: la comparativa corre como tarea propia, liberando el hueco del worker ------------------


@pytest.mark.asyncio
async def test_c1_run_ocr_no_ejecuta_la_comparativa_inline(authapi: Api) -> None:
    """spec: C1 — con el experimento encendido, `run_ocr` persiste el resultado principal y TERMINA
    sin ejecutar la comparativa en el mismo job: la encola como tarea separada. Si corriera inline,
    su fila existiría al volver de `run_ocr`; al correr aparte, AÚN no existe (este test no levanta
    un worker que ejecute la tarea encolada)."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed_pending_upload(dsns, slug="c1-no-inline")
    await set_ocr_experiment_enabled(dsns, True)
    try:
        await run_ocr(
            tenant_id=tenant_id,
            company_id=company_id,
            file_id=file_id,
            extractor=make_comparison_extractor(
                original=build_extracted(), enhanced=build_extracted()
            ),
        )
    finally:
        await set_ocr_experiment_enabled(dsns, False)

    # El resultado principal SÍ quedó persistido por el job...
    assert await fetch_extraction(dsns, file_id=file_id) is not None
    # ...pero la comparativa NO corrió inline: su fila aún no existe porque es una tarea aparte.
    assert await count_comparison_runs(dsns, file_id=file_id) == 0


@pytest.mark.asyncio
async def test_c1_run_ocr_encola_la_comparativa_como_tarea_propia(
    authapi: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec: C1 — al terminar el resultado principal, `run_ocr` encola la comparativa como tarea
    de fondo propia (a través de `enqueue_ocr_comparison`), en vez de ejecutarla en línea."""
    from jobs import ocr as ocr_job  # noqa: PLC0415

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed_pending_upload(dsns, slug="c1-encola")

    enqueued: list[tuple[str, str, str]] = []

    async def _spy(tid: str | UUID, cid: str | UUID, fid: str | UUID) -> None:
        enqueued.append((str(tid), str(cid), str(fid)))

    monkeypatch.setattr(ocr_job, "enqueue_ocr_comparison", _spy)

    await set_ocr_experiment_enabled(dsns, True)
    try:
        await run_ocr(
            tenant_id=tenant_id,
            company_id=company_id,
            file_id=file_id,
            extractor=make_comparison_extractor(
                original=build_extracted(), enhanced=build_extracted()
            ),
        )
    finally:
        await set_ocr_experiment_enabled(dsns, False)

    assert enqueued == [(tenant_id, company_id, file_id)]


@pytest.mark.asyncio
async def test_c1_comparativa_como_tarea_persiste_su_fila(authapi: Api) -> None:
    """spec: C1 — la tarea de comparativa, cuando corre, hace el mismo trabajo que antes: lee la
    imagen realzada y persiste su fila en `ocr_comparison_runs`, sin tocar el resultado principal
    ya persistido. La tarea re-descarga las páginas del almacén (no recibe bytes por la cola)."""
    from jobs.ocr import run_ocr_comparison_task  # noqa: PLC0415

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed_pending_upload(dsns, slug="c1-task")
    extractor = make_comparison_extractor(original=build_extracted(), enhanced=build_extracted())

    await set_ocr_experiment_enabled(dsns, True)
    try:
        await run_ocr(
            tenant_id=tenant_id, company_id=company_id, file_id=file_id, extractor=extractor
        )
        assert await count_comparison_runs(dsns, file_id=file_id) == 0

        # Ahora corre la tarea de fondo (con el extractor inyectado, sin worker ni proveedor real).
        await run_ocr_comparison_task({}, tenant_id, company_id, file_id, extractor=extractor)
    finally:
        await set_ocr_experiment_enabled(dsns, False)

    assert await count_comparison_runs(dsns, file_id=file_id) == 1
    # El resultado principal sigue intacto (la comparativa nunca lo toca).
    assert await fetch_extraction(dsns, file_id=file_id) is not None


@pytest.mark.asyncio
async def test_c1_interruptor_apagado_no_encola_comparativa(
    authapi: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec: C1 / invariante — con el experimento apagado, el resultado principal se persiste y NO
    se encola ninguna comparativa (coste cero), igual que hoy."""
    from jobs import ocr as ocr_job  # noqa: PLC0415

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed_pending_upload(dsns, slug="c1-off")

    enqueued: list[tuple[str, str, str]] = []

    async def _spy(tid: str | UUID, cid: str | UUID, fid: str | UUID) -> None:
        enqueued.append((str(tid), str(cid), str(fid)))

    monkeypatch.setattr(ocr_job, "enqueue_ocr_comparison", _spy)
    await set_ocr_experiment_enabled(dsns, False)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_comparison_extractor(original=build_extracted(), enhanced=build_extracted()),
    )

    assert enqueued == []


# --- C3: las páginas de una multipágina se descargan en paralelo ---------------------------------


@pytest.mark.asyncio
async def test_c3_paginas_multipagina_se_descargan_en_paralelo(
    authapi: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec: C3 — con varias páginas, las descargas se lanzan a la vez (el total tiende al máximo,
    no a la suma). Se fuerza la multipágina espiando `get_document_pages` (3 ubicaciones de la misma
    imagen real) y `storage.get_object` con una latencia artificial para distinguir serie de
    paralelo. Con el extractor doble (instantáneo), el total debe acercarse al tramo paralelo."""
    from invoice_intake import repository as intake_repo  # noqa: PLC0415
    from invoice_intake import storage  # noqa: PLC0415
    from jobs import ocr as ocr_job  # noqa: PLC0415
    from shared.db import tenant_session  # noqa: PLC0415

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed_pending_upload(dsns, slug="c3-par")
    await set_ocr_experiment_enabled(dsns, False)

    async with tenant_session(UUID(tenant_id), UUID(company_id)) as session:
        real_locations = await intake_repo.get_document_pages(session, UUID(file_id))
    triple = [real_locations[0], real_locations[0], real_locations[0]]

    async def _three_pages(session, fid):  # noqa: ANN001, ANN202, ARG001
        return triple

    DELAY = 0.4
    real_get = storage.get_object

    def _slow_get(bucket: str, key: str) -> bytes:
        time.sleep(DELAY)
        return real_get(bucket, key)

    monkeypatch.setattr(ocr_job.intake_repo, "get_document_pages", _three_pages)
    monkeypatch.setattr(ocr_job.storage, "get_object", _slow_get)

    started = time.monotonic()
    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_comparison_extractor(original=build_extracted(), enhanced=build_extracted()),
    )
    elapsed = time.monotonic() - started

    # Serie sería ~3 x DELAY = 1.2s SOLO de descarga (más el OCR). Paralelo ~DELAY = 0.4s. Exigimos
    # bastante menos que la suma secuencial, con margen para no hacer el test frágil.
    assert elapsed < (3 * DELAY), (
        f"las descargas parecen secuenciales: {elapsed:.2f}s para 3 páginas con {DELAY}s de "
        "latencia simulada cada una"
    )


# --- C4: un proveedor colgado se corta mucho antes que 8 minutos ---------------------------------


def test_c4_timeout_de_proveedor_es_acotado_y_coherente_con_el_lease() -> None:
    """spec: C4 — el timeout de la llamada al proveedor es muy inferior a los 8 minutos actuales
    (un proveedor colgado no puede retener el hueco del worker mucho más allá de la mediana real de
    ~15s), y el lease del claim no es menor que ese timeout (si lo fuera, un worker vivo y sano
    perdería su claim a mitad de una lectura legítima)."""
    from shared.config import get_settings  # noqa: PLC0415

    settings = get_settings()
    # Muy superior a la mediana real (~15s) y a su máximo observado (~52s), muy inferior a 8 min.
    assert settings.ocr_provider_timeout_seconds <= 150, (
        f"timeout de proveedor {settings.ocr_provider_timeout_seconds}s demasiado holgado: un "
        "proveedor colgado retiene el worker mucho más de lo razonable"
    )
    # Coherencia: el lease debe cubrir al menos el timeout, si no un worker sano perdería su claim.
    assert settings.ocr_claim_lease_seconds >= settings.ocr_provider_timeout_seconds, (
        "el lease del claim no puede ser menor que el timeout del proveedor"
    )
