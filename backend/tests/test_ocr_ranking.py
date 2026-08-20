"""Tests de comportamiento S4.8: ranking multi-modelo enganchado al worker OCR
(spec docs/specs/S4.8-panel-ranking-multimodelo.md).

Criterios C1, C2, C4, C8, C9. Postgres real + MinIO real, con dobles de extractor inyectados (nunca
se llama a ningún proveedor real). C3 (motor sin configurar) se prueba a nivel unitario en
`test_ranking_engines.py`; C5-C7 (Mistral/Azure DocIntel/prompt compartido) ya cubiertos en los
tests dedicados de cada extractor.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from tests._dbtest import seed_company, seed_tenant, seed_user
from tests._ocr import (
    OWN_CIF,
    build_extracted,
    count_ranking_entries,
    fetch_ranking_entries,
    make_counting_extractor,
    make_extractor,
    ranking_entries_visible_as_tenant,
    real_jpeg_bytes,
    run_ocr,
    seed_uploaded_file,
    seed_uploaded_file_page,
    set_ocr_experiment_enabled,
)

Api = tuple[object, dict[str, str]]


async def _seed(dsns: dict[str, str], *, slug: str, **file_kwargs) -> tuple[str, str, str]:
    tenant_id = await seed_tenant(dsns["admin"], slug, f"{slug.upper()} Asesoría")
    user_id = await seed_user(
        dsns["admin"], tenant_id=tenant_id, email=f"ana@{slug}.es", role="user"
    )
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Mi Empresa", cif=OWN_CIF
    )
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=user_id, **file_kwargs
    )
    return tenant_id, company_id, file_id


async def test_c1_interruptor_apagado_no_genera_entradas_de_ranking(authapi: Api) -> None:
    """C1: con el interruptor apagado (valor por defecto), cero entradas y cero coste extra."""
    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, False)
    tenant_id, company_id, file_id = await _seed(dsns, slug="rk-c1")

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted()),
    )

    assert await count_ranking_entries(dsns, file_id=file_id) == 0


async def test_c2_interruptor_encendido_genera_una_entrada_por_motor(authapi: Api) -> None:
    """C2: cada motor disponible deja su propia entrada, con su lectura y puntuación."""
    from jobs.ocr_ranking import run_ocr_ranking
    from ocr.extraction import DocumentPage

    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_id, company_id, file_id = await _seed(dsns, slug="rk-c2")

    await run_ocr_ranking(
        tenant_id,
        company_id,
        file_id,
        pages=[DocumentPage(b"bytes de la factura", "image/jpeg")],
        own_cif=OWN_CIF,
        extractors=[
            make_extractor(build_extracted(engine="gemini-3-flash", model="gemini-3-flash")),
            make_extractor(build_extracted(engine="claude-vertex", model="claude-x")),
        ],
    )

    entries = await fetch_ranking_entries(dsns, file_id=file_id)
    engines = {e["engine"] for e in entries}
    assert engines == {"gemini-3-flash", "claude-vertex"}
    assert all(e["score"] == 5 for e in entries)  # lectura perfecta por defecto de build_extracted


async def test_ranking_cierra_la_sesion_antes_de_llamar_a_los_motores(
    authapi: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El ranking solo abre Postgres para consultar el interruptor y persistir los resultados."""
    import jobs.ocr_ranking as ranking_job
    from ocr.extraction import DocumentPage

    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_id, company_id, file_id = await _seed(dsns, slug="ranking-short-session")
    original_session = ranking_job.tenant_session
    active_sessions = 0

    @asynccontextmanager
    async def tracked_session(*args, **kwargs):
        nonlocal active_sessions
        async with original_session(*args, **kwargs) as session:
            active_sessions += 1
            try:
                yield session
            finally:
                active_sessions -= 1

    class Extractor:
        async def extract(self, _content: bytes, _content_type: str):
            assert active_sessions == 0
            return build_extracted(engine="short-session-engine")

    monkeypatch.setattr(ranking_job, "tenant_session", tracked_session)
    await ranking_job.run_ocr_ranking(
        tenant_id,
        company_id,
        file_id,
        pages=[DocumentPage(b"ranking document", "image/jpeg")],
        own_cif=OWN_CIF,
        extractors=[Extractor()],
    )

    entries = await fetch_ranking_entries(dsns, file_id=file_id)
    assert [entry["engine"] for entry in entries] == ["short-session-engine"]


async def test_c4_el_fallo_de_un_motor_no_bloquea_a_los_demas(authapi: Api) -> None:
    """C4: un motor que falla en esta factura no deja entrada; los demás sí."""
    from jobs.ocr_ranking import run_ocr_ranking
    from ocr.extraction import DocumentPage, InvoiceExtractionError

    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_id, company_id, file_id = await _seed(dsns, slug="rk-c4")

    await run_ocr_ranking(
        tenant_id,
        company_id,
        file_id,
        pages=[DocumentPage(b"x", "image/jpeg")],
        own_cif=OWN_CIF,
        extractors=[
            make_extractor(build_extracted(engine="gemini-3-flash")),
            make_extractor(error=InvoiceExtractionError("timeout")),
        ],
    )

    entries = await fetch_ranking_entries(dsns, file_id=file_id)
    assert len(entries) == 1
    assert entries[0]["engine"] == "gemini-3-flash"


async def test_c8_reprocesar_no_duplica_las_entradas(authapi: Api) -> None:
    """C8: reprocesar hace upsert por `(uploaded_file_id, engine)`, no duplica."""
    from jobs.ocr_ranking import run_ocr_ranking
    from ocr.extraction import DocumentPage

    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_id, company_id, file_id = await _seed(dsns, slug="rk-c8")
    extractors = [make_extractor(build_extracted(engine="gemini-3-flash"))]

    for _ in range(2):
        await run_ocr_ranking(
            tenant_id,
            company_id,
            file_id,
            pages=[DocumentPage(b"x", "image/jpeg")],
            own_cif=OWN_CIF,
            extractors=extractors,
        )

    assert await count_ranking_entries(dsns, file_id=file_id) == 1


async def test_c9_aislamiento_por_tenant(authapi: Api) -> None:
    """C9: el ranking de un tenant nunca es visible desde el contexto RLS de otro."""
    from jobs.ocr_ranking import run_ocr_ranking
    from ocr.extraction import DocumentPage

    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_a, company_a, file_a = await _seed(dsns, slug="rk-c9a")
    tenant_b, _company_b, _file_b = await _seed(dsns, slug="rk-c9b")

    await run_ocr_ranking(
        tenant_a,
        company_a,
        file_a,
        pages=[DocumentPage(b"x", "image/jpeg")],
        own_cif=OWN_CIF,
        extractors=[make_extractor(build_extracted(engine="gemini-3-flash"))],
    )

    assert await ranking_entries_visible_as_tenant(dsns, tenant_id=tenant_a) == 1
    assert await ranking_entries_visible_as_tenant(dsns, tenant_id=tenant_b) == 0


async def test_ranking_multipagina_procesa_todas_las_hojas(authapi: Api) -> None:
    """El ranking legado recibe el documento entero, nunca solo los bytes de la raíz."""
    from jobs.ocr_ranking import run_ocr_ranking
    from ocr.extraction import DocumentPage

    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_id, company_id, file_id = await _seed(dsns, slug="rk-multipage")
    await seed_uploaded_file_page(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        root_uploaded_file_id=file_id,
        page_number=2,
        content=b"second ranking page",
    )
    observed_pages: list[int] = []

    class PageExtractor:
        async def extract(self, _content: bytes, _content_type: str):
            raise AssertionError("no debe reducirse a una página")

        async def extract_pages(self, pages):
            observed_pages.append(len(pages))
            return build_extracted(engine="gemini-3-flash")

    await run_ocr_ranking(
        tenant_id,
        company_id,
        file_id,
        pages=[
            DocumentPage(b"first ranking page", "image/jpeg"),
            DocumentPage(b"second ranking page", "image/jpeg"),
        ],
        own_cif=OWN_CIF,
        extractors=[PageExtractor()],
    )

    assert observed_pages == [2]
    assert await count_ranking_entries(dsns, file_id=file_id) == 1


async def test_s6_7_el_ocr_principal_no_dispara_el_ranking_legado(authapi: Api) -> None:
    """S6.7 conserva el código legado, pero lo retira del fan-out del OCR principal."""
    from jobs.ocr import run_ocr_comparison_task

    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_id, company_id, file_id = await _seed(
        dsns, slug="rk-c2-nodup", content=real_jpeg_bytes()
    )

    default_extractor = make_counting_extractor(build_extracted(engine="gemini-3-flash"))

    try:
        await run_ocr(
            tenant_id=tenant_id,
            company_id=company_id,
            file_id=file_id,
            extractor=default_extractor,
        )
        await run_ocr_comparison_task(
            {}, tenant_id, company_id, file_id, extractor=default_extractor
        )
    finally:
        await set_ocr_experiment_enabled(dsns, False)

    # Con el interruptor ON, la comparativa original-vs-realzada (S2.9/S2.10) reutiliza el MISMO
    # extractor inyectado para su segunda lectura ("enhanced") — eso es una llamada legítima de
    # esta tarea, no del ranking legado. El ranking legado (S4.8) llamaría a un extractor POR CADA
    # motor configurado (varios objetos distintos); aquí solo hay un único extractor y solo se
    # espera su segunda invocación desde la comparativa, nunca una tercera.
    assert default_extractor.calls == 2
    assert await count_ranking_entries(dsns, file_id=file_id) == 0
