"""Suite anti-cruce de tenants v1 (gate de CI bloqueante — plan §8, spec docs/specs/S1.7).

Demuestra, endpoint a endpoint, que un usuario del tenant A no puede leer ni escribir nada de B:
- **Vector 403** (token de A en el subdominio de B): `current_identity` rechaza el token cuyo
  `tenant_id` no casa con el subdominio (S1.3/S1.6). Se recorre la lista COMPLETA de protegidos.
- **Vector 404** (por id ajeno): operar por id sobre un recurso de B desde el contexto de A -> la
  RLS de S1.1 tapa la fila (no existe en el contexto de A).
- **Guard de cobertura**: ningún endpoint de negocio nuevo escapa del gate sin que salte el test.

No reimplementa el aislamiento; lo prueba. Si un test falla, el bug se corrige en el código de
aislamiento, no relajando el criterio. El nivel de datos (sin `app.tenant_id` -> 0 filas) ya está en
`test_tenancy_rls.py` (S1.1); aquí se cubre la superficie HTTP.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from tests._auth import USER_PASSWORD, USER_PASSWORD_HASH, bearer, host, login
from tests._companies import VALID_CIF, VALID_CIF_2, XLSX_MIME, build_xlsx
from tests._dbtest import seed_company, seed_tenant, seed_user
from tests._intake import JPEG, JPEG_CT, upload_parts
from tests._invoicing import seed_invoice

pytestmark = pytest.mark.isolation

Api = tuple[httpx.AsyncClient, dict[str, str]]

API = "/api/v1"

# Rutas públicas (no exigen identidad): quedan fuera del anti-cruce. (metodo, plantilla OpenAPI)
_PUBLIC_ROUTES = {
    ("GET", f"{API}/health"),
    ("GET", f"{API}/tenants/current"),
    ("GET", f"{API}/manifest.webmanifest"),
    ("POST", f"{API}/auth/login"),
    ("POST", f"{API}/auth/refresh"),
    ("POST", f"{API}/auth/logout"),
    ("POST", f"{API}/auth/activate"),
    ("POST", f"{API}/auth/activate/confirm"),
    ("POST", f"{API}/register"),
}

# Endpoints de negocio cubiertos por el vector 403 (token de A en subdominio de B).
_PROTECTED_ROUTES = {
    ("GET", f"{API}/auth/me"),
    ("GET", f"{API}/companies"),
    ("POST", f"{API}/companies"),
    ("PATCH", f"{API}/companies/{{company_id}}"),
    ("DELETE", f"{API}/companies/{{company_id}}"),
    ("POST", f"{API}/companies/import"),
    ("POST", f"{API}/uploads"),
    ("GET", f"{API}/uploads/{{file_id}}/download-url"),
    ("GET", f"{API}/uploads/{{file_id}}/review"),
    ("POST", f"{API}/uploads/{{file_id}}/confirm"),
    ("GET", f"{API}/invoices/history"),
    ("PATCH", f"{API}/invoices/{{invoice_id}}"),
    ("POST", f"{API}/invoices/test/purge"),
    ("GET", f"{API}/reporting/invoices"),
    ("GET", f"{API}/reporting/invoices/export"),
    ("GET", f"{API}/reporting/companies"),
    ("GET", f"{API}/registrations"),
    ("POST", f"{API}/registrations/{{user_id}}/approve"),
    ("POST", f"{API}/registrations/{{user_id}}/reject"),
    ("POST", f"{API}/platform/tenants"),
    ("GET", f"{API}/platform/tenants"),
    ("GET", f"{API}/platform/tenants/metrics"),
    ("POST", f"{API}/platform/tenants/{{tenant_id}}/convert-to-production"),
    ("POST", f"{API}/platform/tenants/{{tenant_id}}/purge"),
}


def _requests_para_403(dummy_id: str) -> list[tuple[str, str, dict[str, object]]]:
    """Peticiones concretas (cuerpo válido) para ejercitar cada endpoint protegido en el vector 403.

    El cuerpo es válido: el 403 debe venir de `current_identity` (token<->subdominio), no de un 422
    por cuerpo mal formado. En rutas con `{id}` el id da igual (el 403 ocurre antes).
    """
    return [
        ("GET", f"{API}/auth/me", {}),
        ("GET", f"{API}/companies", {}),
        ("POST", f"{API}/companies", {"json": {"name": "X", "cif": VALID_CIF}}),
        ("PATCH", f"{API}/companies/{dummy_id}", {"json": {"name": "X"}}),
        ("DELETE", f"{API}/companies/{dummy_id}", {}),
        (
            "POST",
            f"{API}/companies/import",
            {"files": {"file": ("x.xlsx", build_xlsx([]), XLSX_MIME)}},
        ),
        (
            "POST",
            f"{API}/uploads",
            upload_parts(JPEG, dummy_id, filename="f.jpg", content_type=JPEG_CT),
        ),
        ("GET", f"{API}/uploads/{dummy_id}/download-url", {}),
        ("GET", f"{API}/uploads/{dummy_id}/review", {}),
        ("POST", f"{API}/uploads/{dummy_id}/confirm", {"json": {"direction": "recibida"}}),
        ("GET", f"{API}/invoices/history", {}),
        ("PATCH", f"{API}/invoices/{dummy_id}", {"json": {"total_amount": "1.00"}}),
        ("POST", f"{API}/invoices/test/purge", {}),
        ("GET", f"{API}/reporting/invoices", {}),
        ("GET", f"{API}/reporting/invoices/export", {}),
        ("GET", f"{API}/reporting/companies", {}),
        ("GET", f"{API}/registrations", {}),
        ("POST", f"{API}/registrations/{dummy_id}/approve", {}),
        ("POST", f"{API}/registrations/{dummy_id}/reject", {}),
        ("POST", f"{API}/platform/tenants", {"json": {"name": "X", "slug": "coladaxyz"}}),
        ("GET", f"{API}/platform/tenants", {}),
        ("GET", f"{API}/platform/tenants/metrics", {}),
        ("POST", f"{API}/platform/tenants/{dummy_id}/convert-to-production", {}),
        ("POST", f"{API}/platform/tenants/{dummy_id}/purge", {}),
    ]


async def _token(client: httpx.AsyncClient, hostname: str, email: str) -> str:
    resp = await login(client, hostname, email, USER_PASSWORD)
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def _seed_tenant_admin(dsns: dict[str, str], *, slug: str, cif: str) -> tuple[str, str, str]:
    """Siembra un tenant con `tenant_admin` y una empresa. Devuelve (tid, email, company_id)."""
    tenant_id = await seed_tenant(dsns["admin"], slug, f"{slug.upper()} Asesoría")
    admin_email = f"admin@{slug}.es"
    await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email=admin_email,
        role="tenant_admin",
        password_hash=USER_PASSWORD_HASH,
    )
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name=f"Empresa {slug}", cif=cif
    )
    return tenant_id, admin_email, company_id


# --- C1: vector 403 (token de A en subdominio de B) ---------------------------------------------


async def test_c1_token_de_a_rechazado_en_subdominio_de_b(authapi: Api) -> None:
    """C1: un token de `ilex` usado en `otra.localhost` da 403 en TODO endpoint protegido."""
    client, dsns = authapi
    _, admin_ilex, _ = await _seed_tenant_admin(dsns, slug="ilex", cif=VALID_CIF)
    await _seed_tenant_admin(
        dsns, slug="otra", cif=VALID_CIF_2
    )  # el subdominio 'otra' debe resolver
    token_ilex = await _token(client, "ilex.localhost", admin_ilex)

    for method, path, kwargs in _requests_para_403(str(uuid4())):
        resp = await client.request(
            method, path, headers={**host("otra.localhost"), **bearer(token_ilex)}, **kwargs
        )
        assert resp.status_code == 403, (
            f"{method} {path}: esperado 403, obtenido {resp.status_code}"
        )


# --- C2: vector 404 (por id ajeno desde el contexto propio) -------------------------------------


async def test_c2_operar_por_id_ajeno_da_404(authapi: Api) -> None:
    """C2: operar por id sobre recurso de `otra` desde el contexto de `ilex` -> 404 (RLS)."""
    client, dsns = authapi
    _, admin_ilex, _ = await _seed_tenant_admin(dsns, slug="ilex", cif=VALID_CIF)
    tid_otra, _, company_otra = await _seed_tenant_admin(dsns, slug="otra", cif=VALID_CIF_2)
    # un usuario pendiente en 'otra' (para intentar aprobar/rechazar por id ajeno)
    user_otra = await seed_user(
        dsns["admin"],
        tenant_id=tid_otra,
        email="pend@otra.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
        status="pending",
    )
    invoice_otra = await seed_invoice(dsns, tenant_id=tid_otra, company_id=company_otra)
    token_ilex = await _token(client, "ilex.localhost", admin_ilex)
    propio = lambda: {**host("ilex.localhost"), **bearer(token_ilex)}  # noqa: E731

    casos = [
        ("PATCH", f"{API}/companies/{company_otra}", {"json": {"name": "hack"}}),
        ("DELETE", f"{API}/companies/{company_otra}", {}),
        ("POST", f"{API}/registrations/{user_otra}/approve", {}),
        ("POST", f"{API}/registrations/{user_otra}/reject", {}),
        ("PATCH", f"{API}/invoices/{invoice_otra}", {"json": {"total_amount": "1.00"}}),
    ]
    for method, path, kwargs in casos:
        resp = await client.request(method, path, headers=propio(), **kwargs)
        assert resp.status_code == 404, (
            f"{method} {path}: esperado 404, obtenido {resp.status_code}"
        )


# --- C3: las lecturas de A no incluyen datos de B -----------------------------------------------


async def test_c3_lecturas_acotadas_al_propio_tenant(authapi: Api) -> None:
    """C3: `GET /companies` de `ilex` no trae ni una empresa de `otra`."""
    client, dsns = authapi
    tid_ilex, admin_ilex, _ = await _seed_tenant_admin(dsns, slug="ilex", cif=VALID_CIF)
    await _seed_tenant_admin(dsns, slug="otra", cif=VALID_CIF_2)
    token_ilex = await _token(client, "ilex.localhost", admin_ilex)

    lista = await client.get(
        f"{API}/companies", headers={**host("ilex.localhost"), **bearer(token_ilex)}
    )
    assert lista.status_code == 200
    cifs = {c["cif"] for c in lista.json()}
    assert VALID_CIF in cifs  # ve la suya
    assert VALID_CIF_2 not in cifs  # nunca la de 'otra'


# --- C4: las escrituras no cruzan de tenant (incluido el registro público) ----------------------


async def test_c4_registro_publico_escribe_solo_en_su_subdominio(authapi: Api) -> None:
    """C4: un `POST /register` en `otra.localhost` escribe solo en `otra`, nunca en `ilex`."""
    import asyncpg

    client, dsns = authapi
    tid_ilex, _, _ = await _seed_tenant_admin(dsns, slug="ilex", cif=VALID_CIF)
    await _seed_tenant_admin(dsns, slug="otra", cif=VALID_CIF_2)

    resp = await client.post(
        f"{API}/register",
        json={
            "email": "nuevo@correo.es",
            "company_name": "Nueva SL",
            "cif": "76072394D",
            "password": USER_PASSWORD,
        },
        headers=host("otra.localhost"),
    )
    assert resp.status_code in (201, 202)

    conn = await asyncpg.connect(dsns["admin"])
    try:
        en_ilex = await conn.fetchval(
            "SELECT count(*) FROM users WHERE tenant_id = $1 AND email = 'nuevo@correo.es'",
            tid_ilex,
        )
    finally:
        await conn.close()
    assert en_ilex == 0  # el alta en 'otra' no aparece en 'ilex'


# --- C5: guard anti-olvido de cobertura ---------------------------------------------------------


def test_c5_todo_endpoint_de_negocio_esta_cubierto() -> None:
    """C5: todo endpoint de negocio (OpenAPI) está cubierto; uno sin cubrir hace fallar el test."""
    from main import create_app

    paths = create_app().openapi()["paths"]
    del_negocio: set[tuple[str, str]] = set()
    for path, operations in paths.items():
        if not path.startswith(API):
            continue
        for method in operations:
            ruta = (method.upper(), path)
            if ruta not in _PUBLIC_ROUTES:
                del_negocio.add(ruta)

    sin_cubrir = del_negocio - _PROTECTED_ROUTES
    assert not sin_cubrir, (
        f"Endpoints de negocio sin cobertura anti-cruce (añádelos a la suite S1.7): {sin_cubrir}"
    )
