"""Tests de comportamiento S6.2: laboratorio OCR (diagnóstico por factura, admin-tech), spec
docs/specs/S6.2-laboratorio-ocr-admin-tech.md. Criterios C1-C13.

Observable vía HTTP (cliente ASGI), autenticado como `platform_admin` (host `panel.localhost`) para
el laboratorio en sí, y como identidad de tenant (host `<slug>.localhost`) para sembrar/confirmar
una factura real de extremo a extremo antes de diagnosticarla. Contra Postgres real.
"""

from __future__ import annotations

import httpx

from tests._dbtest import seed_company, seed_tenant
from tests._intake import JPEG, JPEG_CT
from tests._invoicing import auth, confirm_body, confirm_url, seed_confirmable, seed_invoice
from tests._ocr import seed_ranking_entry
from tests._platform import platform_token, seed_platform_admin

Api = tuple[httpx.AsyncClient, dict[str, str]]


def _platform_auth(token: str) -> dict[str, str]:
    return {"Host": "panel.localhost", "Authorization": f"Bearer {token}"}


async def _admin_tech_token(client: httpx.AsyncClient, dsns: dict[str, str]) -> str:
    await seed_platform_admin(dsns, is_admin_tech=True)
    return await platform_token(client)


async def _seed_confirmed_invoice(
    dsns: dict[str, str],
    client: httpx.AsyncClient,
    *,
    slug: str = "ilex",
    invoice_number: str | None = "F-2026-001",
) -> dict:
    """Siembra y confirma una factura de extremo a extremo (S2.3+S2.5 reales, no un atajo): da un
    `ocr_extractions` real (con `raw`) y, tras el `POST confirm`, una `invoices` real + su diff en
    `ocr_corrections` si algo cambió respecto al OCR.

    `counterparty_name`/`invoice_number` se alinean explícitamente entre `seed_confirmable` (OCR) y
    `confirm_body` (lo confirmado): sus valores por defecto DIFIEREN a propósito ("Prov SA"/`None`
    vs "Proveedor SA"/"F-2026-001", usados por otros tests para probar el diff de correcciones) —
    aquí, sin alinearlos, cualquier factura "confirmada sin cambios" generaría 2 correcciones
    fantasma."""
    s = await seed_confirmable(dsns, client, slug=slug, invoice_number=invoice_number)
    resp = await client.post(
        confirm_url(s["file_id"]),
        headers=auth(s["token"], f"{slug}.localhost"),
        json=confirm_body(counterparty_name="Prov SA", invoice_number=invoice_number),
    )
    assert resp.status_code == 201, resp.text
    return {**s, "invoice_id": resp.json()["id"]}


def _lab_url(tenant_id: str, file_id: str) -> str:
    return f"/api/v1/platform/tenants/{tenant_id}/invoices/{file_id}/lab"


def _invoices_url(tenant_id: str) -> str:
    return f"/api/v1/platform/tenants/{tenant_id}/invoices"


def _image_url(tenant_id: str, file_id: str) -> str:
    return f"/api/v1/platform/tenants/{tenant_id}/invoices/{file_id}/image"


# --- Área A: control de acceso y navegación --------------------------------------------------


async def test_c1_sin_admin_tech_el_listado_da_403(authapi: Api) -> None:
    """spec: S6.2 C1 — un `platform_admin` sin `is_admin_tech` no puede listar facturas de ningún
    tenant desde el laboratorio."""
    client, dsns = authapi
    await seed_platform_admin(dsns, is_admin_tech=False)
    token = await platform_token(client)
    tenant_id = await seed_tenant(dsns["admin"], "ilex", "ILEX")

    resp = await client.get(_invoices_url(tenant_id), headers=_platform_auth(token))

    assert resp.status_code == 403, resp.text


async def test_c1b_sin_admin_tech_el_laboratorio_de_una_factura_da_403(authapi: Api) -> None:
    """spec: S6.2 C1 — igual que arriba, para el endpoint del laboratorio de una factura
    concreta."""
    client, dsns = authapi
    s = await _seed_confirmed_invoice(dsns, client)
    await seed_platform_admin(dsns, is_admin_tech=False)
    token = await platform_token(client)

    resp = await client.get(_lab_url(s["tenant_id"], s["file_id"]), headers=_platform_auth(token))

    assert resp.status_code == 403, resp.text


async def test_c2_con_admin_tech_lista_las_facturas_confirmadas_del_tenant_elegido(
    authapi: Api,
) -> None:
    """spec: S6.2 C2 — con el flag, ve el listado de facturas confirmadas del tenant elegido."""
    client, dsns = authapi
    s = await _seed_confirmed_invoice(dsns, client, slug="ilex")
    token = await _admin_tech_token(client, dsns)

    resp = await client.get(_invoices_url(s["tenant_id"]), headers=_platform_auth(token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1, body
    assert body[0]["uploaded_file_id"] == s["file_id"]


async def test_c2b_lista_mas_de_50_facturas_confirmadas_sin_truncar(authapi: Api) -> None:
    """Regresión de auditoría: `list_tenant_invoices` reutilizaba el repositorio PAGINADO del panel
    (pide como mucho `PAGE_SIZE + 1 = 51` filas para que el llamante recorte a una página) — un
    tenant con más de 50 facturas confirmadas perdía en silencio todas las anteriores, sin ningún
    aviso ni forma de ver el resto desde el laboratorio. `list_all` (sin paginar, mismo criterio que
    `list_for_export`) lo corrige."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "ilex", "ILEX")
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Mi Empresa", cif="B00000000"
    )
    for i in range(55):
        await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id, days_ago=i)
    token = await _admin_tech_token(client, dsns)

    resp = await client.get(_invoices_url(tenant_id), headers=_platform_auth(token))

    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 55, "se truncó el listado del laboratorio por debajo de 55 facturas"


async def test_c4_tenant_inexistente_da_404(authapi: Api) -> None:
    """spec: S6.2 C4 — un `tenant_id` que no existe da 404 explícito, no una lista vacía."""
    client, dsns = authapi
    token = await _admin_tech_token(client, dsns)
    import uuid  # noqa: PLC0415

    resp = await client.get(_invoices_url(str(uuid.uuid4())), headers=_platform_auth(token))

    assert resp.status_code == 404, resp.text
    # No un 404 genérico de FastAPI por ruta inexistente: uno explícito del propio dominio (mismo
    # mensaje que ya usa `export_tenant`, S4.7) — evita que este test "pase" solo porque la ruta
    # todavía no existe en absoluto.
    assert resp.json()["detail"] == "No existe ese tenant", resp.text


async def test_c5_fichero_de_otro_tenant_da_404(authapi: Api) -> None:
    """spec: S6.2 C5 — pedir el laboratorio de un fichero de OTRO tenant (no el elegido) da 404."""
    client, dsns = authapi
    setex = await _seed_confirmed_invoice(dsns, client, slug="setex")
    ilex_tenant_id = await seed_tenant(dsns["admin"], "ilex", "ILEX")
    token = await _admin_tech_token(client, dsns)

    # Pide el laboratorio del fichero de `setex`, pero indicando el tenant `ilex`.
    resp = await client.get(
        _lab_url(ilex_tenant_id, setex["file_id"]), headers=_platform_auth(token)
    )

    assert resp.status_code == 404, resp.text
    # Mismo motivo que arriba: un mensaje explícito del dominio, no el 404 genérico de una ruta
    # que todavía no existe en absoluto.
    assert resp.json()["detail"] == "Factura no encontrada", resp.text


# --- Área B: Lectura 1 (IA cruda) -------------------------------------------------------------


async def test_c6_lectura_1_devuelve_el_raw_del_proveedor(authapi: Api) -> None:
    """spec: S6.2 C6 — la Lectura 1 es la respuesta cruda del proveedor, sin procesar."""
    client, dsns = authapi
    s = await _seed_confirmed_invoice(dsns, client)
    token = await _admin_tech_token(client, dsns)

    resp = await client.get(_lab_url(s["tenant_id"], s["file_id"]), headers=_platform_auth(token))

    assert resp.status_code == 200, resp.text
    reading_1 = resp.json()["reading_1"]
    assert "raw" in reading_1
    assert reading_1["raw"] is not None


async def test_c7_lectura_1_indica_el_motor_que_leyo(authapi: Api) -> None:
    """spec: S6.2 C7 — la Lectura 1 indica qué motor la produjo."""
    client, dsns = authapi
    s = await _seed_confirmed_invoice(dsns, client)
    token = await _admin_tech_token(client, dsns)

    resp = await client.get(_lab_url(s["tenant_id"], s["file_id"]), headers=_platform_auth(token))

    reading_1 = resp.json()["reading_1"]
    assert reading_1["engine"], reading_1
    assert reading_1["model"], reading_1


# --- Área C: Lectura 2 (tras ajustes internos) ------------------------------------------------


async def test_c8_lectura_2_muestra_campos_confianzas_y_veredicto(authapi: Api) -> None:
    """spec: S6.2 C8 — la Lectura 2 muestra campos, confianzas, veredicto de contraparte y avisos,
    igual que la pantalla de confirmación en su día."""
    client, dsns = authapi
    s = await _seed_confirmed_invoice(dsns, client)
    token = await _admin_tech_token(client, dsns)

    resp = await client.get(_lab_url(s["tenant_id"], s["file_id"]), headers=_platform_auth(token))

    reading_2 = resp.json()["reading_2"]
    assert "fields" in reading_2
    assert "confidences" in reading_2
    assert "counterparty_verdict" in reading_2
    assert reading_2["counterparty_verdict"]["status"] == "valid"


async def test_c9_lectura_2_funciona_para_una_factura_ya_confirmada(authapi: Api) -> None:
    """spec: S6.2 C9 — a diferencia de `review()`, sirve la Lectura 2 aunque el fichero YA esté
    `confirmed` (fuera de `_CONFIRMABLE_STATES`)."""
    client, dsns = authapi
    s = await _seed_confirmed_invoice(dsns, client)
    token = await _admin_tech_token(client, dsns)

    resp = await client.get(_lab_url(s["tenant_id"], s["file_id"]), headers=_platform_auth(token))

    # El propio 200 con reading_2 ya demuestra que no se bloqueó por NotConfirmable/estado.
    assert resp.status_code == 200, resp.text
    assert resp.json()["reading_2"] is not None


# --- Área D: Lectura 3 (guardado final) -------------------------------------------------------


async def test_c10_lectura_3_muestra_la_factura_y_el_diff_de_correcciones(authapi: Api) -> None:
    """spec: S6.2 C10 — la Lectura 3 muestra la factura final y las correcciones humanas."""
    client, dsns = authapi
    s = await seed_confirmable(dsns, client)
    # Confirma con un total DISTINTO al que sembró el OCR (121.00) -> genera una corrección real.
    resp = await client.post(
        confirm_url(s["file_id"]),
        headers=auth(s["token"]),
        json=confirm_body(total="199.00"),
    )
    assert resp.status_code == 201, resp.text
    token = await _admin_tech_token(client, dsns)

    lab = await client.get(_lab_url(s["tenant_id"], s["file_id"]), headers=_platform_auth(token))

    reading_3 = lab.json()["reading_3"]
    assert reading_3["invoice"]["total_amount"] == "199.00"
    fields_corrected = {c["field"] for c in reading_3["corrections"]}
    assert "total_amount" in fields_corrected


async def test_c11_lectura_3_sin_correcciones_lo_dice_explicito(authapi: Api) -> None:
    """spec: S6.2 C11 — sin ningún cambio del humano, la Lectura 3 lo indica, no una lista vacía
    muda."""
    client, dsns = authapi
    # Confirma exactamente con los mismos valores que sembró el OCR (seed_confirmable/confirm_body
    # comparten los mismos valores por defecto: total 121.00, CIF/fecha/tramos coherentes).
    s = await _seed_confirmed_invoice(dsns, client)
    token = await _admin_tech_token(client, dsns)

    resp = await client.get(_lab_url(s["tenant_id"], s["file_id"]), headers=_platform_auth(token))

    reading_3 = resp.json()["reading_3"]
    assert reading_3["corrections"] == []
    assert reading_3["has_corrections"] is False


# --- Área E: comparativa de modelos -----------------------------------------------------------


async def test_c12_comparativa_con_experimento_encendido_muestra_una_fila_por_motor(
    authapi: Api,
) -> None:
    """spec: S6.2 C12 — con `ocr_ranking_entries` sembradas, la comparativa las muestra ordenadas
    de mayor a menor puntuación."""
    client, dsns = authapi
    s = await _seed_confirmed_invoice(dsns, client)
    await seed_ranking_entry(
        dsns,
        tenant_id=s["tenant_id"],
        company_id=s["company_id"],
        uploaded_file_id=s["file_id"],
        engine="gemini-3-flash",
        score=90,
    )
    await seed_ranking_entry(
        dsns,
        tenant_id=s["tenant_id"],
        company_id=s["company_id"],
        uploaded_file_id=s["file_id"],
        engine="mistral-ocr-4",
        score=10,
    )
    token = await _admin_tech_token(client, dsns)

    resp = await client.get(_lab_url(s["tenant_id"], s["file_id"]), headers=_platform_auth(token))

    ranking = resp.json()["ranking"]
    assert [row["engine"] for row in ranking] == ["gemini-3-flash", "mistral-ocr-4"]
    assert ranking[0]["score"] == 90


async def test_c13_comparativa_sin_experimento_encendido_lo_dice_explicito(authapi: Api) -> None:
    """spec: S6.2 C13 — sin filas de `ocr_ranking_entries` (experimento apagado en su día), la
    comparativa lo indica claramente, no un hueco vacío indistinguible de un error."""
    client, dsns = authapi
    s = await _seed_confirmed_invoice(dsns, client)
    token = await _admin_tech_token(client, dsns)

    resp = await client.get(_lab_url(s["tenant_id"], s["file_id"]), headers=_platform_auth(token))

    body = resp.json()
    assert body["ranking"] == []
    assert body["ranking_available"] is False


# --- "Ver" (foto original, spec C2) -----------------------------------------------------------


async def test_ver_devuelve_la_foto_original_de_la_factura(authapi: Api) -> None:
    """spec: S6.2 C2 — el botón "Ver" de cada fila muestra la foto original de la factura."""
    client, dsns = authapi
    s = await _seed_confirmed_invoice(dsns, client)
    token = await _admin_tech_token(client, dsns)

    resp = await client.get(_image_url(s["tenant_id"], s["file_id"]), headers=_platform_auth(token))

    assert resp.status_code == 200, resp.text
    assert resp.content == JPEG
    assert resp.headers["content-type"] == JPEG_CT


async def test_ver_de_un_fichero_de_otro_tenant_da_404(authapi: Api) -> None:
    """spec: S6.2 C5 — mismo criterio anti-cruce de tenants que el resto del laboratorio."""
    client, dsns = authapi
    setex = await _seed_confirmed_invoice(dsns, client, slug="setex")
    ilex_tenant_id = await seed_tenant(dsns["admin"], "ilex", "ILEX")
    token = await _admin_tech_token(client, dsns)

    resp = await client.get(
        _image_url(ilex_tenant_id, setex["file_id"]), headers=_platform_auth(token)
    )

    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Factura no encontrada", resp.text
