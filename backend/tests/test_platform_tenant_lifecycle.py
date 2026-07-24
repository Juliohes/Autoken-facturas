"""Tests de comportamiento S4.7: ciclo de vida completo de un tenant (spec
docs/specs/S4.7-ciclo-de-vida-tenant.md). Criterios C1-C16.

En fichero propio (no `test_platform_tenants.py`, que ya reúne S4.1/S4.4/S4.5/S4.6 y supera las 900
líneas): suspender/exportar/borrar es un bloque de comportamiento propio y bastante más pesado
(genera ficheros ZIP reales, descarga de MinIO real) que merece su propia unidad de test.

Observable vía HTTP (cliente ASGI), autenticado como `platform_admin`, contra Postgres y MinIO
reales.
"""

from __future__ import annotations

import asyncio
import io
import json
import uuid
import zipfile
from datetime import UTC, datetime

import httpx

from invoice_intake import storage
from tests._auth import USER_PASSWORD, USER_PASSWORD_HASH, bearer, host, login
from tests._counterparty import fetch_cif_lookup, seed_cif_lookup, seed_counterparty
from tests._dbtest import seed_branding, seed_company, seed_membership, seed_tenant, seed_user
from tests._intake import JPEG
from tests._invoicing import fetch_invoice_by_id, seed_invoice
from tests._ocr import seed_uploaded_file
from tests._platform import (
    fetch_tenant_by_id,
    platform_token,
    seed_audit_log,
    seed_invoice_edit,
    seed_ocr_correction,
    seed_ocr_extraction,
    seed_platform_admin,
)

Api = tuple[httpx.AsyncClient, dict[str, str]]

URL = "/api/v1/platform/tenants"


def _auth(token: str) -> dict[str, str]:
    return {**host("panel.localhost"), **bearer(token)}


async def _download_zip(download_url: str) -> zipfile.ZipFile:
    async with httpx.AsyncClient() as raw:
        resp = await raw.get(download_url)
    assert resp.status_code == 200, resp.text
    return zipfile.ZipFile(io.BytesIO(resp.content))


# --- Suspender / reactivar (C1-C4) -----------------------------------------------------------


async def test_c1_suspender_bloquea_el_login_sin_tocar_datos(authapi: Api) -> None:
    """C1: suspender -> login falla; los datos siguen intactos."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "clientex", "Cliente X SL")
    await seed_company(dsns["admin"], tenant_id=tenant_id, name="A", cif="A39031620")
    await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="admin@clientex.es",
        role="tenant_admin",
        password_hash=USER_PASSWORD_HASH,
    )
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.post(f"{URL}/{tenant_id}/suspend", headers=_auth(token))

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "suspended"
    login_resp = await login(client, "clientex.localhost", "admin@clientex.es", USER_PASSWORD)
    assert login_resp.status_code == 401
    tenant = await fetch_tenant_by_id(dsns, tenant_id=tenant_id)
    assert tenant is not None
    assert tenant["name"] == "Cliente X SL"


async def test_c2_reactivar_revierte_el_bloqueo(authapi: Api) -> None:
    """C2: reactivar -> el login vuelve a funcionar."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "clientex", "Cliente X SL", status="suspended")
    await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="admin@clientex.es",
        role="tenant_admin",
        password_hash=USER_PASSWORD_HASH,
    )
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.post(f"{URL}/{tenant_id}/reactivate", headers=_auth(token))

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active"
    login_resp = await login(client, "clientex.localhost", "admin@clientex.es", USER_PASSWORD)
    assert login_resp.status_code == 200


async def test_c3_suspender_y_reactivar_son_idempotentes(authapi: Api) -> None:
    """C3: suspender un tenant ya suspendido (o reactivar uno ya activo) no es un error."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "clientex", "Cliente X SL")
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp_reactivate = await client.post(f"{URL}/{tenant_id}/reactivate", headers=_auth(token))
    resp_suspend_1 = await client.post(f"{URL}/{tenant_id}/suspend", headers=_auth(token))
    resp_suspend_2 = await client.post(f"{URL}/{tenant_id}/suspend", headers=_auth(token))

    assert resp_reactivate.status_code == 200
    assert resp_suspend_1.status_code == 200
    assert resp_suspend_2.status_code == 200
    assert resp_suspend_2.json()["status"] == "suspended"


async def test_suspender_y_reactivar_conservan_el_dominio_propio_ya_asignado(authapi: Api) -> None:
    """Regresión (auditoría de arquitectura): `TenantRecord.custom_domain` solo lo rellenan las
    funciones cuyo `SELECT` lo incluye; si `suspend_tenant`/`reactivate_tenant` lo olvidaran algún
    día, este test lo detectaría (en vez de fallar en silencio con `None`, S4.6 x S4.7)."""
    client, dsns = authapi
    tenant_id = await seed_tenant(
        dsns["admin"], "clientex", "Cliente X SL", custom_domain="facturas.clientex.es"
    )
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp_suspend = await client.post(f"{URL}/{tenant_id}/suspend", headers=_auth(token))
    resp_reactivate = await client.post(f"{URL}/{tenant_id}/reactivate", headers=_auth(token))

    assert resp_suspend.json()["custom_domain"] == "facturas.clientex.es"
    assert resp_reactivate.json()["custom_domain"] == "facturas.clientex.es"


async def test_c4_suspender_y_reactivar_404_si_no_existe(authapi: Api) -> None:
    """C4: id inexistente -> 404 en ambos."""
    client, dsns = authapi
    await seed_platform_admin(dsns)
    token = await platform_token(client)
    dummy = uuid.uuid4()

    resp_suspend = await client.post(f"{URL}/{dummy}/suspend", headers=_auth(token))
    resp_reactivate = await client.post(f"{URL}/{dummy}/reactivate", headers=_auth(token))

    assert resp_suspend.status_code == 404
    assert resp_reactivate.status_code == 404


# --- Exportar (C5-C8) --------------------------------------------------------------------------


async def test_c5_exportar_genera_un_zip_completo_y_descargable(authapi: Api) -> None:
    """C5: el ZIP contiene un JSON por tabla con las filas reales y los ficheros subidos."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "clientex", "Cliente X SL")
    company_id = await seed_company(dsns["admin"], tenant_id=tenant_id, name="A", cif="A39031620")
    await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id, days_ago=0)
    uploader = await seed_user(dsns["admin"], tenant_id=tenant_id, email="u@clientex.es")
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=uploader
    )
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.post(f"{URL}/{tenant_id}/export", headers=_auth(token))

    assert resp.status_code == 200, resp.text
    zip_file = await _download_zip(resp.json()["download_url"])
    names = zip_file.namelist()
    assert "companies.json" in names
    assert "invoices.json" in names
    companies = json.loads(zip_file.read("companies.json"))
    assert len(companies) == 1
    assert companies[0]["name"] == "A"
    invoices = json.loads(zip_file.read("invoices.json"))
    assert len(invoices) == 1
    matching_files = [n for n in names if n.startswith(f"files/{file_id}")]
    assert len(matching_files) == 1
    assert zip_file.read(matching_files[0]) == JPEG


async def test_c6_exportar_marca_last_export_at(authapi: Api) -> None:
    """C6: tras exportar, una lectura posterior muestra `last_export_at` no nulo."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "clientex", "Cliente X SL")
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.post(f"{URL}/{tenant_id}/export", headers=_auth(token))

    assert resp.status_code == 200, resp.text
    tenant = await fetch_tenant_by_id(dsns, tenant_id=tenant_id)
    assert tenant is not None
    assert tenant["last_export_at"] is not None


async def test_c7_anticruce_el_export_de_un_tenant_no_incluye_datos_de_otro(authapi: Api) -> None:
    """C7: exportar A nunca trae datos de B."""
    client, dsns = authapi
    tenant_a = await seed_tenant(dsns["admin"], "tenanta", "Tenant A")
    tenant_b = await seed_tenant(dsns["admin"], "tenantb", "Tenant B")
    await seed_company(dsns["admin"], tenant_id=tenant_a, name="Empresa A", cif="A39031620")
    await seed_company(dsns["admin"], tenant_id=tenant_b, name="Empresa B", cif="B06183446")
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.post(f"{URL}/{tenant_a}/export", headers=_auth(token))

    assert resp.status_code == 200, resp.text
    zip_file = await _download_zip(resp.json()["download_url"])
    companies = json.loads(zip_file.read("companies.json"))
    assert [c["name"] for c in companies] == ["Empresa A"]


async def test_c8_exportar_un_tenant_sin_datos_no_falla(authapi: Api) -> None:
    """C8: tenant recién creado, sin nada -> 200, ZIP con JSONs vacíos, sin error."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "vacio", "Vacío SL")
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.post(f"{URL}/{tenant_id}/export", headers=_auth(token))

    assert resp.status_code == 200, resp.text
    zip_file = await _download_zip(resp.json()["download_url"])
    assert json.loads(zip_file.read("companies.json")) == []
    assert not any(n.startswith("files/") and n != "files/" for n in zip_file.namelist())


async def test_exportar_incluye_las_12_tablas_con_datos_reales(authapi: Api) -> None:
    """Cobertura completa (auditoría de cobertura): las 12 tablas del inventario, no solo
    `companies`/`invoices`, traen datos reales cuando existen."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "clientex", "Cliente X SL")
    await seed_branding(dsns["admin"], tenant_id=tenant_id, app_name="Cliente X")
    company_id = await seed_company(dsns["admin"], tenant_id=tenant_id, name="A", cif="A39031620")
    employee = await seed_user(dsns["admin"], tenant_id=tenant_id, email="empleado@clientex.es")
    await seed_membership(
        dsns["admin"], user_id=employee, company_id=company_id, tenant_id=tenant_id
    )
    await seed_counterparty(dsns, tenant_id=tenant_id, cif="B06183446", name="Proveedor SA")
    invoice_id = await seed_invoice(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        days_ago=0,
        tax_lines=[{"iva_pct": "21", "base": "100.00", "cuota": "21.00"}],
    )
    invoice = await fetch_invoice_by_id(dsns, invoice_id=invoice_id)
    assert invoice is not None
    uploaded_file_id = str(invoice["uploaded_file_id"])
    await seed_invoice_edit(
        dsns, tenant_id=tenant_id, company_id=company_id, invoice_id=invoice_id, edited_by=employee
    )
    await seed_ocr_correction(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        invoice_id=invoice_id,
        uploaded_file_id=uploaded_file_id,
        corrected_by=employee,
    )
    await seed_ocr_extraction(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=employee
    )
    await seed_audit_log(dsns, tenant_id=tenant_id, at=datetime.now(UTC))
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.post(f"{URL}/{tenant_id}/export", headers=_auth(token))

    assert resp.status_code == 200, resp.text
    zip_file = await _download_zip(resp.json()["download_url"])
    tables = {
        "tenant_branding",
        "users",
        "companies",
        "memberships",
        "uploaded_files",
        "ocr_extractions",
        "counterparties",
        "invoices",
        "invoice_tax_lines",
        "ocr_corrections",
        "invoice_edits",
        "audit_log",
    }
    for table in tables:
        rows = json.loads(zip_file.read(f"{table}.json"))
        assert len(rows) >= 1, f"{table}.json debería tener al menos una fila"


async def test_exportar_dos_veces_seguidas_genera_dos_zips_distintos(authapi: Api) -> None:
    """Caso límite §5: exportar dos veces no sobrescribe el anterior (regresión real, encontrada
    por la auditoría de cobertura: la clave del export solo tenía precisión de segundo)."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "clientex", "Cliente X SL")
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp_1 = await client.post(f"{URL}/{tenant_id}/export", headers=_auth(token))
    resp_2 = await client.post(f"{URL}/{tenant_id}/export", headers=_auth(token))

    assert resp_1.status_code == 200, resp_1.text
    assert resp_2.status_code == 200, resp_2.text
    assert resp_1.json()["download_url"] != resp_2.json()["download_url"]
    # Las dos descargas siguen funcionando: el segundo export no pisó al primero.
    zip_1 = await _download_zip(resp_1.json()["download_url"])
    zip_2 = await _download_zip(resp_2.json()["download_url"])
    assert zip_1.namelist() == zip_2.namelist()


async def test_exportar_un_tenant_suspendido_funciona_igual_que_uno_activo(authapi: Api) -> None:
    """Caso límite §5: suspender no bloquea ninguna operación de plataforma, solo el login."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "clientex", "Cliente X SL", status="suspended")
    await seed_company(dsns["admin"], tenant_id=tenant_id, name="A", cif="A39031620")
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.post(f"{URL}/{tenant_id}/export", headers=_auth(token))

    assert resp.status_code == 200, resp.text
    zip_file = await _download_zip(resp.json()["download_url"])
    assert len(json.loads(zip_file.read("companies.json"))) == 1


async def test_export_404_si_no_existe(authapi: Api) -> None:
    """Id inexistente -> 404 (no cubierto explícitamente por C1-C16, pero mismo criterio que el
    resto del router)."""
    client, dsns = authapi
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.post(f"{URL}/{uuid.uuid4()}/export", headers=_auth(token))

    assert resp.status_code == 404


# --- Borrar (C9-C13) ----------------------------------------------------------------------------


async def test_c9_sin_export_previo_no_se_puede_borrar(authapi: Api) -> None:
    """C9: nunca se exportó -> 409; el tenant sigue existiendo intacto."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "clientex", "Cliente X SL")
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.request(
        "DELETE",
        f"{URL}/{tenant_id}",
        json={"confirm_slug": "clientex"},
        headers=_auth(token),
    )

    assert resp.status_code == 409, resp.text
    assert await fetch_tenant_by_id(dsns, tenant_id=tenant_id) is not None


async def test_c10_slug_de_confirmacion_incorrecto_no_borra_nada(authapi: Api) -> None:
    """C10: `confirm_slug` no coincide -> 422, aunque ya hubiera un export previo válido."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "clientex", "Cliente X SL")
    await seed_platform_admin(dsns)
    token = await platform_token(client)
    await client.post(f"{URL}/{tenant_id}/export", headers=_auth(token))

    resp = await client.request(
        "DELETE",
        f"{URL}/{tenant_id}",
        json={"confirm_slug": "otro-slug"},
        headers=_auth(token),
    )

    assert resp.status_code == 422, resp.text
    assert await fetch_tenant_by_id(dsns, tenant_id=tenant_id) is not None


async def test_c11_con_export_previo_y_slug_correcto_borra_todo(authapi: Api) -> None:
    """C11: exportado + slug correcto -> 204; el tenant y su cascada desaparecen; el bucket
    del tenant también (tras el commit, best-effort, mismo patrón que S4.4)."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "clientex", "Cliente X SL")
    company_id = await seed_company(dsns["admin"], tenant_id=tenant_id, name="A", cif="A39031620")
    uploader = await seed_user(dsns["admin"], tenant_id=tenant_id, email="u@clientex.es")
    await seed_uploaded_file(dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=uploader)
    await seed_platform_admin(dsns)
    token = await platform_token(client)
    await client.post(f"{URL}/{tenant_id}/export", headers=_auth(token))
    assert storage._client().bucket_exists(storage.bucket_for(tenant_id))

    resp = await client.request(
        "DELETE",
        f"{URL}/{tenant_id}",
        json={"confirm_slug": "clientex"},
        headers=_auth(token),
    )

    assert resp.status_code == 204, resp.text
    assert await fetch_tenant_by_id(dsns, tenant_id=tenant_id) is None
    assert not storage._client().bucket_exists(storage.bucket_for(tenant_id))


async def test_borrar_un_tenant_demo_por_la_via_general_funciona_igual_que_uno_real(
    authapi: Api,
) -> None:
    """Caso límite §5: `DELETE` general no exige `is_demo=false` — coexiste con `purge_demo_tenant`
    (S4.4), que sigue siendo el atajo específico para demos sin exigir export previo."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "clientex", "Cliente Demo SL", is_demo=True)
    await seed_platform_admin(dsns)
    token = await platform_token(client)
    await client.post(f"{URL}/{tenant_id}/export", headers=_auth(token))

    resp = await client.request(
        "DELETE",
        f"{URL}/{tenant_id}",
        json={"confirm_slug": "clientex"},
        headers=_auth(token),
    )

    assert resp.status_code == 204, resp.text
    assert await fetch_tenant_by_id(dsns, tenant_id=tenant_id) is None


async def test_borrar_concurrente_del_mismo_tenant_es_atomico(authapi: Api) -> None:
    """Invariante §4: el `FOR UPDATE` serializa dos `DELETE` concurrentes sobre el mismo tenant ya
    exportado — exactamente uno borra (204), el otro no encuentra nada que borrar (404), nunca un
    error inesperado ni un estado inconsistente."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "clientex", "Cliente X SL")
    await seed_platform_admin(dsns)
    token = await platform_token(client)
    await client.post(f"{URL}/{tenant_id}/export", headers=_auth(token))

    resp_1, resp_2 = await asyncio.gather(
        client.request(
            "DELETE",
            f"{URL}/{tenant_id}",
            json={"confirm_slug": "clientex"},
            headers=_auth(token),
        ),
        client.request(
            "DELETE",
            f"{URL}/{tenant_id}",
            json={"confirm_slug": "clientex"},
            headers=_auth(token),
        ),
    )

    statuses = sorted([resp_1.status_code, resp_2.status_code])
    assert statuses == [204, 404], (resp_1.status_code, resp_2.status_code)
    assert await fetch_tenant_by_id(dsns, tenant_id=tenant_id) is None


async def test_c12_borrar_404_si_no_existe(authapi: Api) -> None:
    """C12: id inexistente -> 404."""
    client, dsns = authapi
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.request(
        "DELETE",
        f"{URL}/{uuid.uuid4()}",
        json={"confirm_slug": "loquesea"},
        headers=_auth(token),
    )

    assert resp.status_code == 404


async def test_c13_borrar_nunca_toca_el_bucket_de_exports_ni_cif_lookups(authapi: Api) -> None:
    """C13: el ZIP de export sigue existiendo (descargable) tras borrar el tenant; `cif_lookups`
    no pierde ninguna fila."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "clientex", "Cliente X SL")
    await seed_cif_lookup(
        dsns, cif="A39031620", source="aeat", exists=True, official_name="Empresa X SL"
    )
    await seed_platform_admin(dsns)
    token = await platform_token(client)
    export_resp = await client.post(f"{URL}/{tenant_id}/export", headers=_auth(token))
    download_url = export_resp.json()["download_url"]

    resp = await client.request(
        "DELETE",
        f"{URL}/{tenant_id}",
        json={"confirm_slug": "clientex"},
        headers=_auth(token),
    )

    assert resp.status_code == 204, resp.text
    async with httpx.AsyncClient() as raw:
        still_there = await raw.get(download_url)
    assert still_there.status_code == 200
    assert await fetch_cif_lookup(dsns, cif="A39031620", source="aeat") is not None


# --- RBAC (C14) ----------------------------------------------------------------------------------


async def test_c14_un_tenant_admin_no_puede_usar_ningun_endpoint_del_ciclo_de_vida(
    authapi: Api,
) -> None:
    """C14: token de `tenant_admin` -> 403 en los cuatro endpoints nuevos."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "clientex", "Cliente X SL")
    await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="admin@clientex.es",
        role="tenant_admin",
        password_hash=USER_PASSWORD_HASH,
    )
    login_resp = await login(client, "clientex.localhost", "admin@clientex.es", USER_PASSWORD)
    token = login_resp.json()["access_token"]

    resp_suspend = await client.post(f"{URL}/{tenant_id}/suspend", headers=_auth(token))
    resp_reactivate = await client.post(f"{URL}/{tenant_id}/reactivate", headers=_auth(token))
    resp_export = await client.post(f"{URL}/{tenant_id}/export", headers=_auth(token))
    resp_delete = await client.request(
        "DELETE",
        f"{URL}/{tenant_id}",
        json={"confirm_slug": "clientex"},
        headers=_auth(token),
    )

    assert resp_suspend.status_code == 403
    assert resp_reactivate.status_code == 403
    assert resp_export.status_code == 403
    assert resp_delete.status_code == 403
