"""Tests de comportamiento S2.10: comparativa enganchada al worker OCR
(spec docs/specs/S2.9-S2.10-preprocesado-comparativa.md).

Criterios C1-C5, C8, C9. Postgres real + MinIO real (mismo patrón que `test_ocr_worker.py`, S2.3),
con un extractor doble inyectado (nunca se llama a Gemini de verdad) y el interruptor
`ocr_experiment_enabled` (S4.10) manipulado directamente en BD.
"""

from __future__ import annotations

from tests._dbtest import seed_company, seed_tenant, seed_user
from tests._intake import PDF, PDF_CT
from tests._ocr import (
    OWN_CIF,
    build_extracted,
    comparison_runs_visible_as_tenant,
    count_comparison_runs,
    fetch_comparison_run,
    file_status,
    make_comparison_extractor,
    make_extractor,
    real_jpeg_bytes,
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


async def test_c1_interruptor_apagado_no_genera_comparativa(authapi: Api) -> None:
    """C1: con el interruptor apagado (valor por defecto), cero filas y cero coste extra."""
    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, False)
    tenant_id, company_id, file_id = await _seed(dsns, slug="c1", content=real_jpeg_bytes())

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted()),
        ranking_extractors=[],
    )

    assert await count_comparison_runs(dsns, file_id=file_id) == 0
    assert await file_status(dsns, file_id=file_id) == "ocr_done"


async def test_c2_interruptor_encendido_genera_la_comparativa(authapi: Api) -> None:
    """C2: extracción principal en verde + interruptor ON -> se genera la fila de comparativa."""
    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_id, company_id, file_id = await _seed(dsns, slug="c2", content=real_jpeg_bytes())

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted()),
        ranking_extractors=[],
    )

    row = await fetch_comparison_run(dsns, file_id=file_id)
    assert row is not None
    assert row["winner"] == "tie"  # misma lectura para ambas versiones de la imagen
    # El resultado principal es el de siempre, la comparativa no lo cambia.
    assert await file_status(dsns, file_id=file_id) == "ocr_done"


async def test_c3_pdf_no_genera_comparativa(authapi: Api) -> None:
    """C3: un PDF no se realza (no es una foto); el resto del flujo no cambia."""
    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_id, company_id, file_id = await _seed(dsns, slug="c3", content=PDF, content_type=PDF_CT)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted()),
        ranking_extractors=[],
    )

    assert await count_comparison_runs(dsns, file_id=file_id) == 0
    assert await file_status(dsns, file_id=file_id) == "ocr_done"


async def test_c4_extraccion_principal_falla_no_hay_comparativa(authapi: Api) -> None:
    """C4: si la lectura principal falla, no hay baseline exitoso contra el que comparar."""
    from ocr.extraction import InvoiceExtractionError

    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_id, company_id, file_id = await _seed(dsns, slug="c4", content=real_jpeg_bytes())

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(error=InvoiceExtractionError("proveedor caído")),
        ranking_extractors=[],
    )

    assert await count_comparison_runs(dsns, file_id=file_id) == 0
    assert await file_status(dsns, file_id=file_id) == "ocr_failed"


async def test_c5_fallo_de_la_comparativa_no_afecta_al_resultado_principal(authapi: Api) -> None:
    """C5: si la segunda lectura (realzada) falla, el resultado principal queda intacto."""
    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_id, company_id, file_id = await _seed(dsns, slug="c5", content=real_jpeg_bytes())
    buena = build_extracted()

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_comparison_extractor(original=buena, enhanced=buena, error_on="enhanced"),
        ranking_extractors=[],
    )

    assert await count_comparison_runs(dsns, file_id=file_id) == 0
    assert await file_status(dsns, file_id=file_id) == "ocr_done"


async def test_c8_reprocesar_no_duplica_la_comparativa(authapi: Api) -> None:
    """C8: reprocesar el mismo fichero hace upsert, no duplica la fila de comparativa."""
    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_id, company_id, file_id = await _seed(dsns, slug="c8", content=real_jpeg_bytes())

    for _ in range(2):
        await run_ocr(
            tenant_id=tenant_id,
            company_id=company_id,
            file_id=file_id,
            extractor=make_extractor(build_extracted()),
            ranking_extractors=[],
        )

    assert await count_comparison_runs(dsns, file_id=file_id) == 1


async def test_c9_aislamiento_por_tenant(authapi: Api) -> None:
    """C9: la comparativa de un tenant nunca es visible desde el contexto RLS de otro."""
    _client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, True)
    tenant_a, company_a, file_a = await _seed(dsns, slug="c9a", content=real_jpeg_bytes())
    tenant_b, _company_b, _file_b = await _seed(dsns, slug="c9b", content=real_jpeg_bytes())

    await run_ocr(
        tenant_id=tenant_a,
        company_id=company_a,
        file_id=file_a,
        extractor=make_extractor(build_extracted()),
        ranking_extractors=[],
    )

    assert await comparison_runs_visible_as_tenant(dsns, tenant_id=tenant_a) == 1
    assert await comparison_runs_visible_as_tenant(dsns, tenant_id=tenant_b) == 0
