"""Tests de comportamiento S2.3: worker OCR (spec docs/specs/S2.3-worker-ocr.md).

Criterios C1-C11. Observable ejecutando el job del worker sobre un `uploaded_file` sembrado (fichero
real en MinIO) contra Postgres real, con un extractor doble inyectado (el motor real no se llama en
CI). Fase roja: `jobs.ocr.run_ocr` y `ocr.extraction` aún no existen.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from decimal import Decimal

import pytest

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


async def test_irpf_del_ocr_se_persiste_fuera_de_tax_lines(authapi: Api) -> None:
    """Una retención del 19% se conserva como IRPF y el cuadre resta su importe del total."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, slug="ocr-irpf")

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(
            build_extracted(
                total=Decimal("102.00"),
                irpf_rate=Decimal("19"),
                irpf_amount=Decimal("19.00"),
            )
        ),
    )

    row = await fetch_extraction(dsns, file_id=file_id)
    assert row["irpf_rate"] == 19
    assert row["irpf_amount"] == 19
    assert json.loads(row["tax_lines"]) == [{"base": "100.00", "rate": "21", "cuota": "21.00"}]
    assert row["status"] == "auto_ok"


async def test_el_ocr_cierra_la_sesion_antes_de_minio_y_del_extractor(
    authapi: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La descarga y el proveedor no agotan conexiones del pool del tenant mientras esperan."""
    import jobs.ocr as ocr_job

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, slug="ocr-short-session")
    original_session = ocr_job.tenant_session
    original_get_object = ocr_job.storage.get_object
    active_sessions = 0
    external_calls: list[str] = []

    @asynccontextmanager
    async def tracked_session(*args, **kwargs):
        nonlocal active_sessions
        async with original_session(*args, **kwargs) as session:
            active_sessions += 1
            try:
                yield session
            finally:
                active_sessions -= 1

    def tracked_get_object(*args, **kwargs):
        assert active_sessions == 0
        external_calls.append("minio")
        return original_get_object(*args, **kwargs)

    class Extractor:
        async def extract(self, _content: bytes, _content_type: str):
            assert active_sessions == 0
            external_calls.append("ocr")
            return build_extracted()

    monkeypatch.setattr(ocr_job, "tenant_session", tracked_session)
    monkeypatch.setattr(ocr_job.storage, "get_object", tracked_get_object)

    await ocr_job.run_ocr(tenant_id, company_id, file_id, extractor=Extractor())

    assert external_calls == ["minio", "ocr"]
    assert await file_status(dsns, file_id=file_id) == "ocr_done"


async def test_c1b_confidences_indexadas_por_el_mismo_nombre_que_los_campos(authapi: Api) -> None:
    """C1 (regresión, 2026-08-07): `confidences` debe indexarse con el MISMO nombre que `fields`
    en la respuesta de `review` (`total_amount`, `counterparty_tax_id`), no una forma corta.

    Bug real reproducido de extremo a extremo con el worker OCR de verdad (lo reportó Julio: "pone
    No leído pero sí aparece una cantidad que la IA ha sacado, además me pasa varias veces en la
    foto"): `ocr.analysis.analyze_invoice` guardaba `confidences` con claves cortas (`total`,
    `counterparty`) mientras la pantalla de revisión consulta `total_amount`/`counterparty_tax_id`
    (los mismos nombres que `fields`) -> nunca encontraba la confianza real y esos dos campos,
    aunque la IA los hubiera leído con confianza `alta`, siempre se pintaban como "no leído" en
    rojo pese a mostrar el valor leído.
    """
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted()),  # lectura limpia, confianza alta en todo
    )

    row = await fetch_extraction(dsns, file_id=file_id)
    assert row is not None
    confidences = row["confidences"]
    if isinstance(confidences, str):
        import json  # noqa: PLC0415

        confidences = json.loads(confidences)
    assert confidences.get("total_amount") == "alta", confidences
    assert confidences.get("counterparty_tax_id") == "alta", confidences
    assert confidences.get("issue_date") == "alta", confidences


def _confidences(row: dict) -> dict:
    """`row["confidences"]` puede venir como `dict` o como `str` JSON según el driver; normaliza."""
    confidences = row["confidences"]
    if isinstance(confidences, str):
        import json  # noqa: PLC0415

        return json.loads(confidences)
    return confidences


# --- S6.1: número de factura como campo de oro nuevo (spec docs/specs/S6.1-...) -------------------


async def test_s6_1_c1_numero_de_factura_extraido_con_confianza(authapi: Api) -> None:
    """spec: S6.1 C1 — número de factura legible -> persistido con su propia confianza."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted(invoice_number="F-2026-001")),
    )

    row = await fetch_extraction(dsns, file_id=file_id)
    assert row is not None
    assert row["invoice_number"] == "F-2026-001"
    assert _confidences(row).get("invoice_number") == "alta"


async def test_s6_1_c2_numero_de_factura_no_legible_queda_null(authapi: Api) -> None:
    """spec: S6.1 C2 (anti-alucinación) — sin número de factura legible -> null, nunca inventado."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(
            build_extracted(invoice_number=None, invoice_number_confidence="baja")
        ),
    )

    row = await fetch_extraction(dsns, file_id=file_id)
    assert row is not None
    assert row["invoice_number"] is None
    assert _confidences(row).get("invoice_number") == "baja"


async def test_s6_1_c3_numero_de_factura_dudoso_enruta_a_revision(authapi: Api) -> None:
    """spec: S6.1 C3 — número de factura con confianza baja -> needs_review (misma lógica que
    fecha/total/contraparte)."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(
            build_extracted(invoice_number="F-2026-001", invoice_number_confidence="baja")
        ),
    )

    row = await fetch_extraction(dsns, file_id=file_id)
    assert row["status"] == "needs_review"
    assert await file_status(dsns, file_id=file_id) == "needs_review"


# --- S6.1: base imponible e IVA total como campos de oro (Área F, ampliación 2026-08-08) ----------


async def test_s6_1_c25_base_imponible_e_iva_con_confianza_propia(authapi: Api) -> None:
    """spec: S6.1 C25 — base imponible e IVA total ya no quedan huérfanos de confianza."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted()),  # lectura limpia, confianza alta en todo
    )

    row = await fetch_extraction(dsns, file_id=file_id)
    confidences = _confidences(row)
    assert confidences.get("net_amount") == "alta", confidences
    assert confidences.get("tax_amount") == "alta", confidences


async def test_s6_1_c26_base_imponible_no_legible_queda_null(authapi: Api) -> None:
    """spec: S6.1 C26 (anti-alucinación) — sin base imponible/IVA legibles -> null."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(
            build_extracted(net=None, tax=None, net_confidence="baja", tax_confidence="baja")
        ),
    )

    row = await fetch_extraction(dsns, file_id=file_id)
    assert row["net_amount"] is None
    assert row["tax_amount"] is None
    confidences = _confidences(row)
    assert confidences.get("net_amount") == "baja", confidences
    assert confidences.get("tax_amount") == "baja", confidences


async def test_s6_1_c27_base_imponible_dudosa_enruta_a_revision(authapi: Api) -> None:
    """spec: S6.1 C27 — base imponible con confianza baja -> needs_review."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted(net_confidence="baja")),
    )

    assert (await fetch_extraction(dsns, file_id=file_id))["status"] == "needs_review"


async def test_s6_1_c27b_iva_total_dudoso_enruta_a_revision(authapi: Api) -> None:
    """spec: S6.1 C27 — IVA total con confianza baja -> needs_review (mismo criterio, otro
    campo)."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted(tax_confidence="baja")),
    )

    assert (await fetch_extraction(dsns, file_id=file_id))["status"] == "needs_review"


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
            tenant_id=tid,
            company_id=cid,
            file_id=fid,
            extractor=make_extractor(build_extracted()),
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
