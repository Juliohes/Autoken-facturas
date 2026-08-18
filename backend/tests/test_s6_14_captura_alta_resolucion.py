"""Tests de comportamiento S6.14: captura ilegible + degradación de confianza (backend).

Spec: docs/specs/S6.14-captura-alta-resolucion-y-confianza-nombre.md (C6/C7 + casos límite §5).

Contra Postgres/Redis/MinIO reales (mismo estilo que `test_ocr_worker.py`/
`test_invoice_confirm.py`): el worker OCR real (`jobs.ocr.run_ocr`) con un extractor doble
inyectado, y el cliente HTTP ASGI para observar cómo lo ve la persona (`GET review`,
`POST confirm`, `POST retry-ocr`, la purga de facturas de prueba).
"""

from __future__ import annotations

import httpx

from tests._dbtest import seed_company
from tests._intake import (
    JPEG,
    JPEG_CT,
    UPLOADS,
    seed_tenant_admin,
    seed_uploader,
    token_for,
)
from tests._invoicing import (
    auth,
    confirm_body,
    confirm_url,
    fetch_uploaded_file,
    review_url,
    seed_invoice,
)
from tests._ocr import (
    INVALID_COUNTERPARTY_CIF,
    OWN_CIF,
    build_extracted,
    fetch_extraction,
    file_status,
    make_extractor,
    run_ocr,
    seed_uploaded_file,
)

Api = tuple[httpx.AsyncClient, dict[str, str]]

_DETAIL_CAPTURE_UNREADABLE = "La foto no se pudo leer, repite la captura"


async def _seed_tenant_with_company(
    dsns: dict[str, str], *, slug: str = "ilex", email: str = "admin@ilex.es"
) -> tuple[str, str, str]:
    """Siembra tenant + `tenant_admin` + empresa (CIF propio conocido). Devuelve (tenant, admin,
    company)."""
    tenant_id, admin_id = await seed_tenant_admin(dsns, slug=slug, email=email)
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Mi Empresa", cif=OWN_CIF
    )
    return tenant_id, admin_id, company_id


# --- C7: el worker transiciona una captura ilegible a `capture_unreadable` -----------------------


async def test_c7_hard_fail_transiciona_el_fichero_a_capture_unreadable(authapi: Api) -> None:
    _client, dsns = authapi
    tenant_id, admin_id, company_id = await _seed_tenant_with_company(dsns, slug="c7-hard-fail")
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=admin_id
    )

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(
            build_extracted(counterparty_cif=None, total=None, issue_date=None)
        ),
    )

    row = await fetch_extraction(dsns, file_id=file_id)
    assert row is not None
    assert row["status"] == "hard_fail"
    assert await file_status(dsns, file_id=file_id) == "capture_unreadable"


async def test_c7_factura_legible_no_transiciona_a_capture_unreadable(authapi: Api) -> None:
    """Control: una factura legible normal (needs_review de toda la vida) NO es
    capture_unreadable."""
    _client, dsns = authapi
    tenant_id, admin_id, company_id = await _seed_tenant_with_company(dsns, slug="c7-control")
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=admin_id
    )

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted(counterparty_cif=None)),  # solo falta contraparte
    )

    assert await file_status(dsns, file_id=file_id) == "needs_review"


# --- C6: la degradación de confianza persistida se ve en `GET review` ---------------------------


async def test_c6_mod23_invalido_degrada_la_confianza_del_cif_en_review(authapi: Api) -> None:
    client, dsns = authapi
    tenant_id, admin_id, company_id = await _seed_tenant_with_company(dsns, slug="c6-mod23")
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=admin_id
    )
    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(
            build_extracted(counterparty_cif=INVALID_COUNTERPARTY_CIF, counterparty_conf="alta")
        ),
    )
    token = await token_for(client, email="admin@ilex.es", hostname="c6-mod23.localhost")

    resp = await client.get(review_url(file_id), headers=auth(token, "c6-mod23.localhost"))

    assert resp.status_code == 200, resp.text
    assert resp.json()["confidences"]["counterparty_tax_id"] == "baja"


async def test_c6_cuadre_fallido_degrada_la_confianza_del_total_en_review(authapi: Api) -> None:
    client, dsns = authapi
    tenant_id, admin_id, company_id = await _seed_tenant_with_company(dsns, slug="c6-cuadre")
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=admin_id
    )
    from decimal import Decimal

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted(total=Decimal("999.00"))),  # no cuadra con 100+21
    )
    token = await token_for(client, email="admin@ilex.es", hostname="c6-cuadre.localhost")

    resp = await client.get(review_url(file_id), headers=auth(token, "c6-cuadre.localhost"))

    assert resp.status_code == 200, resp.text
    assert resp.json()["confidences"]["total_amount"] == "baja"


# --- C7: review/confirm de una captura ilegible piden repetir la foto, no revisar ----------------


async def test_c7_review_de_captura_ilegible_pide_repetir_la_foto(authapi: Api) -> None:
    client, dsns = authapi
    tenant_id, admin_id, company_id = await _seed_tenant_with_company(dsns, slug="c7-review")
    file_id = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=admin_id,
        status="capture_unreadable",
    )
    token = await token_for(client, email="admin@ilex.es", hostname="c7-review.localhost")

    resp = await client.get(review_url(file_id), headers=auth(token, "c7-review.localhost"))

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == _DETAIL_CAPTURE_UNREADABLE


async def test_c7_confirm_de_captura_ilegible_pide_repetir_la_foto(authapi: Api) -> None:
    client, dsns = authapi
    tenant_id, admin_id, company_id = await _seed_tenant_with_company(dsns, slug="c7-confirm")
    file_id = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=admin_id,
        status="capture_unreadable",
    )
    token = await token_for(client, email="admin@ilex.es", hostname="c7-confirm.localhost")

    resp = await client.post(
        confirm_url(file_id), headers=auth(token, "c7-confirm.localhost"), json=confirm_body()
    )

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == _DETAIL_CAPTURE_UNREADABLE


# --- Reintentos (S6.13): capture_unreadable NO admite reintentar leer la MISMA imagen ------------


async def test_retry_ocr_rechaza_un_fichero_en_capture_unreadable(authapi: Api) -> None:
    client, dsns = authapi
    tenant_id, admin_id, company_id = await _seed_tenant_with_company(dsns, slug="c7-retry")
    file_id = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=admin_id,
        status="capture_unreadable",
    )
    token = await token_for(client, email="admin@ilex.es", hostname="c7-retry.localhost")

    resp = await client.post(
        f"/api/v1/uploads/{file_id}/retry-ocr", headers=auth(token, "c7-retry.localhost")
    )

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "La lectura OCR no se puede reintentar"


# --- Purga de facturas de prueba (S3.5): no debe romperse por el estado nuevo --------------------


async def test_purgar_una_factura_de_prueba_con_fichero_en_capture_unreadable_no_rompe(
    authapi: Api,
) -> None:
    client, dsns = authapi
    tenant_id, admin_id, company_id = await _seed_tenant_with_company(dsns, slug="c7-purge")
    file_id = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=admin_id,
        status="capture_unreadable",
    )
    await seed_invoice(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        is_test=True,
        confirmed_by=admin_id,
        uploaded_file_id=file_id,
    )
    token = await token_for(client, email="admin@ilex.es", hostname="c7-purge.localhost")

    resp = await client.post(
        "/api/v1/invoices/test/purge", headers=auth(token, "c7-purge.localhost")
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"purged": 1}
    assert await fetch_uploaded_file(dsns, file_id=file_id) is None


# --- C8: la nitidez de la captura viaja como telemetría, nunca como bloqueo ----------------------
#
# Contrato con el frontend (`useUploadCapture.ts`): `sharpness_score` es un campo de formulario
# OPCIONAL y de tipo string (la varianza del Laplaciano ya calculada en cliente, serializada). El
# backend NO lo persiste ni lo valida estrictamente (telemetría, no dato de dominio): solo lo
# acepta sin romper y lo loguea como métrica de calidad de captura.

_BATCH_UPLOADS = "/api/v1/uploads/batch"


async def test_c8_subida_con_sharpness_score_se_acepta_y_se_loguea(authapi: Api) -> None:
    """spec: S6.14 C8 — `POST /uploads` con `sharpness_score` -> 201 y la métrica queda logueada."""
    import structlog.testing

    client, dsns = authapi
    _tenant_id, _uid, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    with structlog.testing.capture_logs() as logs:
        resp = await client.post(
            UPLOADS,
            headers=auth(token),
            files={"file": ("captura.jpg", JPEG, JPEG_CT)},
            data={"company_id": company_id, "sharpness_score": "87.3"},
        )

    assert resp.status_code == 201, resp.text
    assert any(
        log.get("event") == "invoice_intake.upload.sharpness_score"
        and log.get("sharpness_score") == "87.3"
        for log in logs
    ), logs


async def test_c8_subida_sin_sharpness_score_sigue_funcionando(authapi: Api) -> None:
    """El campo es opcional ("puede venir ausente"): sin él, la subida sigue siendo un 201 igual."""
    client, dsns = authapi
    _tenant_id, _uid, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    resp = await client.post(
        UPLOADS,
        headers=auth(token),
        files={"file": ("captura.jpg", JPEG, JPEG_CT)},
        data={"company_id": company_id},
    )

    assert resp.status_code == 201, resp.text


async def test_c8_sharpness_score_no_se_valida_estrictamente(authapi: Api) -> None:
    """Un valor no numérico NO rompe la subida (telemetría, no dato de dominio): 201 y se loguea
    crudo, tal cual llegó — parsearlo o no es decisión de quien consuma la métrica, no del intake.
    """
    import structlog.testing

    client, dsns = authapi
    _tenant_id, _uid, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    with structlog.testing.capture_logs() as logs:
        resp = await client.post(
            UPLOADS,
            headers=auth(token),
            files={"file": ("captura.jpg", JPEG, JPEG_CT)},
            data={"company_id": company_id, "sharpness_score": "borrosa"},
        )

    assert resp.status_code == 201, resp.text
    assert any(
        log.get("event") == "invoice_intake.upload.sharpness_score"
        and log.get("sharpness_score") == "borrosa"
        for log in logs
    ), logs


async def test_c8_lote_multipagina_con_sharpness_score_se_acepta_y_se_loguea(authapi: Api) -> None:
    """spec: S6.14 C8 — `POST /uploads/batch` admite el mismo campo opcional (una nitidez de
    conjunto para el documento, si un llamante futuro la calcula: ver `useUploadCapture.ts`)."""
    import structlog.testing

    client, dsns = authapi
    _tenant_id, _uid, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    with structlog.testing.capture_logs() as logs:
        resp = await client.post(
            _BATCH_UPLOADS,
            headers=auth(token),
            files=[
                ("files", ("01.jpg", JPEG + b"-p1", JPEG_CT)),
                ("files", ("02.jpg", JPEG + b"-p2", JPEG_CT)),
            ],
            data={
                "company_id": company_id,
                "direction": "recibida",
                "sharpness_score": "42.0",
            },
        )

    assert resp.status_code == 201, resp.text
    assert any(
        log.get("event") == "invoice_intake.upload.sharpness_score"
        and log.get("sharpness_score") == "42.0"
        for log in logs
    ), logs
