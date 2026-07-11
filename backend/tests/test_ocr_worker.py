"""Tests de comportamiento S2.3: worker OCR (spec docs/specs/S2.3-worker-ocr.md).

Criterios C1-C11. Observable ejecutando el job del worker sobre un `uploaded_file` sembrado (fichero
real en MinIO) contra Postgres real, con un extractor doble inyectado (el motor real no se llama en
CI). Fase roja: `jobs.ocr.run_ocr` y `ocr.extraction` aún no existen.
"""

from __future__ import annotations

from decimal import Decimal

from tests._dbtest import seed_company, seed_tenant, seed_user
from tests._ocr import (
    COUNTERPARTY_CIF,
    INVALID_COUNTERPARTY_CIF,
    OWN_CIF,
    build_extracted,
    count_extractions,
    extractions_visible_as_tenant,
    fetch_extraction,
    file_status,
    make_extractor,
    run_ocr,
    seed_uploaded_file,
)

Api = tuple[object, dict[str, str]]


async def _seed(
    dsns: dict[str, str], *, slug: str = "ilex", cif: str = OWN_CIF
) -> tuple[str, str, str]:
    """Siembra tenant + empleado + empresa (con `cif` propio) + un uploaded_file en pending_ocr."""
    tenant_id = await seed_tenant(dsns["admin"], slug, f"{slug.upper()} Asesoría")
    user_id = await seed_user(
        dsns["admin"], tenant_id=tenant_id, email=f"ana@{slug}.es", role="user"
    )
    company_id = await seed_company(dsns["admin"], tenant_id=tenant_id, name="Mi Empresa", cif=cif)
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=user_id
    )
    return tenant_id, company_id, file_id


async def test_c1_factura_legible_pasa_a_ocr_done(authapi: Api) -> None:
    """C1: factura legible y coherente -> ocr_extractions auto_ok y el fichero en ocr_done."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted()),
    )

    row = await fetch_extraction(dsns, file_id=file_id)
    assert row is not None
    assert row["counterparty_tax_id"] == COUNTERPARTY_CIF
    assert row["own_tax_id_present"] is True
    assert row["status"] == "auto_ok"
    assert await file_status(dsns, file_id=file_id) == "ocr_done"


async def test_c2_campo_no_legible_se_queda_null_no_inventado(authapi: Api) -> None:
    """C2 (anti-alucinación): contraparte no legible -> null persistido, nunca inventado."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted(counterparty_cif=None)),
    )

    row = await fetch_extraction(dsns, file_id=file_id)
    assert row is not None
    assert row["counterparty_tax_id"] is None
    assert row["status"] == "needs_review"
    assert await file_status(dsns, file_id=file_id) == "needs_review"


async def test_c3_contraparte_es_el_cif_que_no_es_el_propio(authapi: Api) -> None:
    """C3: con [propio, otro] leídos, la contraparte es el que NO es el propio (inyectado)."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, cif=OWN_CIF)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(
            build_extracted(own_cif=OWN_CIF, counterparty_cif=COUNTERPARTY_CIF)
        ),
    )

    row = await fetch_extraction(dsns, file_id=file_id)
    assert row["counterparty_tax_id"] == COUNTERPARTY_CIF


async def test_c4_cif_propio_ausente_se_marca(authapi: Api) -> None:
    """C4: si el CIF propio no aparece en la factura -> own_tax_id_present false, needs_review."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted(own_cif=None)),
    )

    row = await fetch_extraction(dsns, file_id=file_id)
    assert row["own_tax_id_present"] is False
    assert row["status"] == "needs_review"
    assert await file_status(dsns, file_id=file_id) == "needs_review"


async def test_c5_cif_contraparte_invalido_se_marca_sin_corregir(authapi: Api) -> None:
    """C5: CIF de contraparte con mód-23 KO -> marcado inválido, valor persistido tal cual."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted(counterparty_cif=INVALID_COUNTERPARTY_CIF)),
    )

    row = await fetch_extraction(dsns, file_id=file_id)
    assert row["counterparty_tax_id"] == INVALID_COUNTERPARTY_CIF  # no se corrige ni se inventa
    assert row["status"] == "needs_review"


async def test_c6_descuadre_aritmetico_se_marca(authapi: Api) -> None:
    """C6: tramos e importe total que no cuadran (fuera de tolerancia) -> descuadre; revisar."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted(total=Decimal("999.00"))),
    )

    assert (await fetch_extraction(dsns, file_id=file_id))["status"] == "needs_review"
    assert await file_status(dsns, file_id=file_id) == "needs_review"


async def test_c7_confianza_media_enruta_a_revision(authapi: Api) -> None:
    """C7: contraparte con confianza media (dudoso) -> needs_review, valor conservado."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted(counterparty_conf="media")),
    )

    row = await fetch_extraction(dsns, file_id=file_id)
    assert row["counterparty_tax_id"] == COUNTERPARTY_CIF
    assert row["status"] == "needs_review"


async def test_c8_identidad_propia_no_se_puntua(authapi: Api) -> None:
    """C8: un nombre propio mal leído NO manda a revisión (lo propio se conoce en companies)."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted(own_cif=OWN_CIF, own_name="Nombre Equivocado SL")),
    )

    row = await fetch_extraction(dsns, file_id=file_id)
    assert row["own_tax_id_present"] is True
    assert row["counterparty_tax_id"] == COUNTERPARTY_CIF
    assert row["status"] == "auto_ok"  # el nombre propio mal leído no puntúa
    assert await file_status(dsns, file_id=file_id) == "ocr_done"


async def test_c9_extraccion_aislada_por_tenant_y_empresa(authapi: Api) -> None:
    """C9: cada tenant solo ve sus extracciones bajo el rol runtime (RLS de dos niveles)."""
    _client, dsns = authapi
    tid_ilex, cid_ilex, fid_ilex = await _seed(dsns, slug="ilex")
    tid_otra, cid_otra, fid_otra = await _seed(dsns, slug="otra")

    for tid, cid, fid in ((tid_ilex, cid_ilex, fid_ilex), (tid_otra, cid_otra, fid_otra)):
        await run_ocr(
            tenant_id=tid, company_id=cid, file_id=fid, extractor=make_extractor(build_extracted())
        )

    # Bajo el rol runtime en contexto de ilex/su empresa: ve la suya y NO la de otra.
    assert await extractions_visible_as_tenant(dsns, tenant_id=tid_ilex, company_id=cid_ilex) == 1
    assert await extractions_visible_as_tenant(dsns, tenant_id=tid_otra, company_id=cid_otra) == 1
    # El superusuario (admin) ve las dos: hay dos filas, aisladas por RLS, no por falta de datos.
    assert await count_extractions(dsns, file_id=fid_ilex) == 1
    assert await count_extractions(dsns, file_id=fid_otra) == 1


async def test_c10_reprocesar_no_duplica(authapi: Api) -> None:
    """C10: reprocesar el mismo fichero deja una sola extracción vigente (idempotente)."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    for _ in range(2):
        await run_ocr(
            tenant_id=tenant_id,
            company_id=company_id,
            file_id=file_id,
            extractor=make_extractor(build_extracted()),
        )

    assert await count_extractions(dsns, file_id=file_id) == 1


async def test_c11_fallo_del_motor_deja_ocr_failed_sin_extraccion(authapi: Api) -> None:
    """C11: si el extractor falla -> el fichero queda en ocr_failed y NO hay extracción parcial."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    from ocr.extraction import InvoiceExtractionError

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(error=InvoiceExtractionError("proveedor caído (test)")),
    )

    assert await file_status(dsns, file_id=file_id) == "ocr_failed"
    assert await count_extractions(dsns, file_id=file_id) == 0
