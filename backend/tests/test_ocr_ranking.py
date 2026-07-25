"""Tests de comportamiento S4.8: ranking multi-modelo enganchado al worker OCR
(spec docs/specs/S4.8-panel-ranking-multimodelo.md).

Criterios C1, C2, C4, C8, C9. Postgres real + MinIO real, con dobles de extractor inyectados (nunca
se llama a ningún proveedor real). C3 (motor sin configurar) se prueba a nivel unitario en
`test_ranking_engines.py`; C5-C7 (Mistral/Azure DocIntel/prompt compartido) ya cubiertos en los
tests dedicados de cada extractor.
"""

from __future__ import annotations

from tests._dbtest import seed_company, seed_tenant, seed_user
from tests._ocr import (
    OWN_CIF,
    build_extracted,
    count_ranking_entries,
    fetch_ranking_entries,
    make_counting_extractor,
    make_extractor,
    ranking_entries_visible_as_tenant,
    run_ocr,
    seed_uploaded_file,
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
        ranking_extractors=[],
    )

    assert await count_ranking_entries(dsns, file_id=file_id) == 0


async def test_c2_interruptor_encendido_genera_una_entrada_por_motor(authapi: Api) -> None:
    """C2: cada motor disponible deja su propia entrada, con su lectura y puntuación."""
    from jobs.ocr_ranking import run_ocr_ranking

    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_id, company_id, file_id = await _seed(dsns, slug="rk-c2")

    await run_ocr_ranking(
        tenant_id,
        company_id,
        file_id,
        content=b"bytes de la factura",
        content_type="image/jpeg",
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


async def test_c4_el_fallo_de_un_motor_no_bloquea_a_los_demas(authapi: Api) -> None:
    """C4: un motor que falla en esta factura no deja entrada; los demás sí."""
    from jobs.ocr_ranking import run_ocr_ranking
    from ocr.extraction import InvoiceExtractionError

    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_id, company_id, file_id = await _seed(dsns, slug="rk-c4")

    await run_ocr_ranking(
        tenant_id,
        company_id,
        file_id,
        content=b"x",
        content_type="image/jpeg",
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

    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_id, company_id, file_id = await _seed(dsns, slug="rk-c8")
    extractors = [make_extractor(build_extracted(engine="gemini-3-flash"))]

    for _ in range(2):
        await run_ocr_ranking(
            tenant_id,
            company_id,
            file_id,
            content=b"x",
            content_type="image/jpeg",
            own_cif=OWN_CIF,
            extractors=extractors,
        )

    assert await count_ranking_entries(dsns, file_id=file_id) == 1


async def test_c9_aislamiento_por_tenant(authapi: Api) -> None:
    """C9: el ranking de un tenant nunca es visible desde el contexto RLS de otro."""
    from jobs.ocr_ranking import run_ocr_ranking

    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_a, company_a, file_a = await _seed(dsns, slug="rk-c9a")
    tenant_b, _company_b, _file_b = await _seed(dsns, slug="rk-c9b")

    await run_ocr_ranking(
        tenant_a,
        company_a,
        file_a,
        content=b"x",
        content_type="image/jpeg",
        own_cif=OWN_CIF,
        extractors=[make_extractor(build_extracted(engine="gemini-3-flash"))],
    )

    assert await ranking_entries_visible_as_tenant(dsns, tenant_id=tenant_a) == 1
    assert await ranking_entries_visible_as_tenant(dsns, tenant_id=tenant_b) == 0


async def test_c2_motor_por_defecto_no_se_llama_dos_veces_por_factura(authapi: Api) -> None:
    """Regresión (auditoría, hallazgo crítico): la lectura del motor por defecto (Gemini Flash) ya
    la calcula `run_ocr` para el resultado principal — el ranking debe reutilizarla, nunca volver a
    llamar a ese motor, o el coste real por factura se duplicaría."""
    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_id, company_id, file_id = await _seed(dsns, slug="rk-c2-nodup")

    default_extractor = make_counting_extractor(build_extracted(engine="gemini-3-flash"))

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=default_extractor,
        ranking_extractors=[
            make_extractor(build_extracted(engine="claude-vertex", model="claude-x"))
        ],
    )

    assert default_extractor.calls == 1  # una vez para el resultado principal, ninguna más

    entries = await fetch_ranking_entries(dsns, file_id=file_id)
    engines = {e["engine"] for e in entries}
    assert engines == {"gemini-3-flash", "claude-vertex"}
