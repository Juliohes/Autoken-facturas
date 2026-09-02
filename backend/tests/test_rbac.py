"""Tests de comportamiento S1.6: RBAC (matriz de permisos + contexto de empresa).

Spec: docs/specs/S1.6-rbac.md, criterios C1-C10. Observable vía HTTP (cliente ASGI con `Host`)
contra Postgres real + Redis, sobre la identidad de S1.3 (`current_identity`) ya mergeada.
Superficie de prueba: `GET /api/v1/companies` (nuevo), `GET /api/v1/auth/me` (ampliado con la
empresa del `user`) y el login de plataforma. Fase roja: el portero de roles, `/companies` y el
contexto de empresa aún no existen.
"""

from __future__ import annotations

import httpx
import pytest

from tenancy.constants import Role
from tests._auth import (
    ME,
    PLATFORM_PASSWORD,
    PLATFORM_PASSWORD_HASH,
    TOTP_SECRET,
    USER_PASSWORD,
    USER_PASSWORD_HASH,
    bearer,
    host,
    login,
    totp_now,
)
from tests._dbtest import seed_company, seed_membership, seed_tenant, seed_user

Api = tuple[httpx.AsyncClient, dict[str, str]]

COMPANIES = "/api/v1/companies"


async def _seed_ilex(dsns: dict[str, str]) -> dict[str, str]:
    """Tenant `ilex` con empresas X e Y, un `user` (empleado de X) y un `tenant_admin`."""
    tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    cx = await seed_company(dsns["admin"], tenant_id=tid, name="Empresa X", cif="A39031620")
    cy = await seed_company(dsns["admin"], tenant_id=tid, name="Empresa Y", cif="B12345674")
    empleado = await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="empleado@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    await seed_membership(dsns["admin"], user_id=empleado, company_id=cx, tenant_id=tid)
    await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="admin@ilex.es",
        role="tenant_admin",
        password_hash=USER_PASSWORD_HASH,
    )
    return {"tid": tid, "cx": cx, "cy": cy, "empleado": empleado}


async def _token(client: httpx.AsyncClient, email: str) -> str:
    """Access token de un usuario de `ilex` (sin TOTP)."""
    resp = await login(client, "ilex.localhost", email, USER_PASSWORD)
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# --- Portero de roles ---------------------------------------------------------------------------


async def test_c1_endpoint_de_tenant_admin_bloquea_al_user(authapi: Api) -> None:
    """C1: `GET /companies` (solo tenant_admin) llamado por un `user` -> 403."""
    client, dsns = authapi
    await _seed_ilex(dsns)
    token = await _token(client, "empleado@ilex.es")
    resp = await client.get(COMPANIES, headers={**host("ilex.localhost"), **bearer(token)})
    assert resp.status_code == 403


async def test_c2_el_rol_permitido_pasa(authapi: Api) -> None:
    """C2: `GET /companies` por un `tenant_admin` -> 200 con las empresas de su asesoría (X e Y)."""
    client, dsns = authapi
    await _seed_ilex(dsns)
    token = await _token(client, "admin@ilex.es")
    resp = await client.get(COMPANIES, headers={**host("ilex.localhost"), **bearer(token)})
    assert resp.status_code == 200
    nombres = {c["name"] for c in resp.json()}
    assert nombres == {"Empresa X", "Empresa Y"}


async def test_c3_sin_token_401_tiene_prioridad_sobre_403(authapi: Api) -> None:
    """C3: un endpoint restringido llamado sin token -> 401 (no autenticado), no 403."""
    client, dsns = authapi
    await _seed_ilex(dsns)
    resp = await client.get(COMPANIES, headers=host("ilex.localhost"))
    assert resp.status_code == 401


async def test_c4_me_abierto_a_cualquier_usuario_autenticado(authapi: Api) -> None:
    """C4: `/auth/me` accesible para `user` y `tenant_admin` (el portero no lo restringe)."""
    client, dsns = authapi
    await _seed_ilex(dsns)
    for email in ("empleado@ilex.es", "admin@ilex.es"):
        token = await _token(client, email)
        resp = await client.get(ME, headers={**host("ilex.localhost"), **bearer(token)})
        assert resp.status_code == 200


# --- Contexto de empresa (scoping por company_id) -----------------------------------------------


async def test_c5_user_corre_en_contexto_de_su_empresa(authapi: Api) -> None:
    """C5: `current_identity` fija la empresa del `user`; `/auth/me` reporta su empresa (X)."""
    client, dsns = authapi
    await _seed_ilex(dsns)
    token = await _token(client, "empleado@ilex.es")
    me = await client.get(ME, headers={**host("ilex.localhost"), **bearer(token)})
    assert me.status_code == 200
    company = me.json().get("company")
    assert company is not None and company["name"] == "Empresa X"


async def test_c6_tenant_admin_corre_en_contexto_de_asesoria(authapi: Api) -> None:
    """C6: un `tenant_admin` no queda acotado a una empresa; `/auth/me` reporta empresa null."""
    client, dsns = authapi
    await _seed_ilex(dsns)
    token = await _token(client, "admin@ilex.es")
    me = await client.get(ME, headers={**host("ilex.localhost"), **bearer(token)})
    assert me.status_code == 200
    assert me.json().get("company") is None


async def test_c7_user_sin_exactamente_una_empresa_se_rechaza(authapi: Api) -> None:
    """C7: un `user` con 0 o >1 empresas activas -> 403 (cuenta mal configurada), sin datos."""
    client, dsns = authapi
    seeded = await _seed_ilex(dsns)
    tid = seeded["tid"]
    # user sin ninguna membership
    await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="sin@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    # user con dos memberships (X e Y)
    dos = await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="dos@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    await seed_membership(dsns["admin"], user_id=dos, company_id=seeded["cx"], tenant_id=tid)
    await seed_membership(dsns["admin"], user_id=dos, company_id=seeded["cy"], tenant_id=tid)

    for email in ("sin@ilex.es", "dos@ilex.es"):
        token = await _token(client, email)
        resp = await client.get(ME, headers={**host("ilex.localhost"), **bearer(token)})
        assert resp.status_code == 403, f"{email}: {resp.status_code}"


# --- Rol de plataforma (cierra #53) -------------------------------------------------------------


async def test_c8_platform_admin_solo_hace_login_por_panel(authapi: Api) -> None:
    """C8: `platform_admin` hace login en `panel`; en subdominio u otro host -> rechazado."""
    client, dsns = authapi
    await seed_user(
        dsns["admin"],
        tenant_id=None,
        email="julio@autoken.es",
        role="platform_admin",
        password_hash=PLATFORM_PASSWORD_HASH,
        totp_secret=TOTP_SECRET,
    )
    en_panel = await login(
        client, "panel.localhost", "julio@autoken.es", PLATFORM_PASSWORD, totp_code=totp_now()
    )
    assert en_panel.status_code == 200
    # en un host no-tenant que no es panel, el login de plataforma no se acepta
    otro_host = await login(
        client, "app.localhost", "julio@autoken.es", PLATFORM_PASSWORD, totp_code=totp_now()
    )
    assert otro_host.status_code == 401


async def test_c9_platform_admin_no_accede_a_datos_de_tenant_por_subdominio(authapi: Api) -> None:
    """C9: el token de un `platform_admin` en un endpoint de negocio de tenant -> 403 (S1.3 C11)."""
    client, dsns = authapi
    await _seed_ilex(dsns)
    await seed_user(
        dsns["admin"],
        tenant_id=None,
        email="julio@autoken.es",
        role="platform_admin",
        password_hash=PLATFORM_PASSWORD_HASH,
        totp_secret=TOTP_SECRET,
    )
    login_resp = await login(
        client, "panel.localhost", "julio@autoken.es", PLATFORM_PASSWORD, totp_code=totp_now()
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    resp = await client.get(COMPANIES, headers={**host("ilex.localhost"), **bearer(token)})
    assert resp.status_code == 403


# --- Rechazo de host multi-etiqueta (auditoría S1.6 A1) -----------------------------------------


async def test_platform_admin_no_hace_login_por_host_multietiqueta(authapi: Api) -> None:
    """A1: `panel.foo.localhost` no es el panel canónico -> el login de plataforma se rechaza.

    Defensa en profundidad: un `Host` multi-etiqueta manipulado no debe hacerse pasar por `panel`
    (ni por un subdominio de tenant), sin confiar en que el proxy inverso sanee `Host`.
    """
    client, dsns = authapi
    await seed_user(
        dsns["admin"],
        tenant_id=None,
        email="julio@autoken.es",
        role="platform_admin",
        password_hash=PLATFORM_PASSWORD_HASH,
        totp_secret=TOTP_SECRET,
    )
    canonico = await login(
        client, "panel.localhost", "julio@autoken.es", PLATFORM_PASSWORD, totp_code=totp_now()
    )
    assert canonico.status_code == 200  # el panel canónico sí acepta el login
    multietiqueta = await login(
        client, "panel.foo.localhost", "julio@autoken.es", PLATFORM_PASSWORD, totp_code=totp_now()
    )
    assert multietiqueta.status_code == 401  # host multi-etiqueta: no es el panel


# --- Allowlist de rol para el contexto RLS (auditoría S1.6 A2) -----------------------------------


def test_scope_for_role_deniega_roles_no_contemplados() -> None:
    """A2: la decisión de contexto RLS es una allowlist; un rol no contemplado se deniega.

    No se puede sembrar un rol inválido en BD (lo veta el CHECK de `users`), así que se prueba la
    función de decisión directamente: `user`/`tenant_admin` obtienen su contexto y cualquier otro
    rol levanta `RoleNotAuthorized` (que el llamante traduce a 403), nunca visibilidad amplia.
    """
    from identity.scoping import RlsScope, RoleNotAuthorized, scope_for_role

    assert scope_for_role(Role.USER) is RlsScope.COMPANY
    assert scope_for_role(Role.TENANT_ADMIN) is RlsScope.TENANT
    for role in (Role.PLATFORM_ADMIN, "auditor", "root", "superuser", ""):
        with pytest.raises(RoleNotAuthorized):
            scope_for_role(role)


# --- Guard anti-olvido de la matriz -------------------------------------------------------------

# Rutas públicas (no exigen identidad): health, resolución del tenant y todo el flujo de login/
# activación previo a tener sesión. Se listan por (método, path) para no dejar la puerta abierta a
# que una futura ruta pública sin identidad se cuele sin justificar.
_PUBLIC_ROUTES = frozenset(
    {
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/metrics"),  # agregados operativos, nunca datos de tenant (S5.6)
        ("GET", "/api/v1/tenants/current"),
        ("GET", "/api/v1/manifest.webmanifest"),
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/refresh"),
        ("POST", "/api/v1/auth/logout"),
        ("POST", "/api/v1/auth/activate"),
        ("POST", "/api/v1/auth/activate/confirm"),
        # Registro autoservicio (S1.4): público en el subdominio a propósito (no hay token; el
        # contexto se abre desde el host). Se acota por RLS del subdominio + rate-limit por IP.
        ("POST", "/api/v1/register"),
        # Recuperación de contraseña y verificación de email (PROMPT-AUTOFACTU-AUTH-COMPLETO,
        # bloques 1/2): públicas por el mismo motivo -- sin token, el portero es el rate-limit +
        # el token de un solo uso, no `require_roles`.
        ("POST", "/api/v1/auth/password/forgot"),
        ("POST", "/api/v1/auth/password/reset"),
        ("POST", "/api/v1/auth/register/verify-email"),
    }
)
# Rutas abiertas a propósito a cualquier usuario autenticado (exigen identidad, pero no restringen
# por rol): `/auth/me` es el testigo de la propia identidad.
_OPEN_AUTHENTICATED = frozenset({("GET", "/api/v1/auth/me")})
# Verbos de negocio a inspeccionar (los que mutan o leen datos del tenant).
_BUSINESS_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


def _collect_api_routes(routes: object) -> list[object]:
    """Aplana las `APIRoute` de la app descendiendo por los routers incluidos.

    FastAPI 0.137+ incluye los routers de forma perezosa (`_IncludedRouter`), así que `app.routes`
    no expone las `APIRoute` directamente: hay que bajar a `original_router.routes`. Robusto frente
    a esa mecánica interna (la razón por la que la enumeración canónica sale del OpenAPI).
    """
    from fastapi.routing import APIRoute

    collected: list[object] = []
    for route in routes:  # type: ignore[union-attr]
        if isinstance(route, APIRoute):
            collected.append(route)
        else:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                collected.extend(_collect_api_routes(inner.routes))
    return collected


def _api_routes(app: object) -> dict[tuple[str, str], object]:
    """Mapa (MÉTODO, path completo) -> `APIRoute`, con el prefijo de la API reconstruido.

    `APIRoute.path` lleva solo el prefijo propio del router (p. ej. `/auth/me`); el prefijo de la
    API (`/api/v1`, aplicado en `include_router`) se antepone para casar con los paths del OpenAPI.
    """
    from shared.config import get_settings

    prefix = get_settings().api_prefix
    mapa: dict[tuple[str, str], object] = {}
    for route in _collect_api_routes(app.routes):  # type: ignore[attr-defined]
        full_path = prefix + route.path  # type: ignore[attr-defined]
        for method in route.methods:  # type: ignore[attr-defined]
            mapa[(method, full_path)] = route
    return mapa


async def test_c10_toda_ruta_de_negocio_declara_sus_roles(authapi: Api) -> None:
    """C10: denegar por defecto: TODA operación de negocio (cualquier método) declara sus roles.

    La enumeración parte del esquema OpenAPI (`app.openapi()["paths"]`), que lista paths y métodos
    en cualquier versión de FastAPI (robusto frente a cambios internos de `app.routes`, p. ej. la
    inclusión perezosa de routers de FastAPI 0.137). Para cada operación que no está en la allowlist
    de rutas públicas ni en la de abiertas a propósito, se inspecciona `route.dependant` y se exige
    que el portero de roles esté declarado; si una de negocio se queda sin roles, el test falla.
    """
    from identity.authz import declared_roles, requires_authentication
    from main import create_app

    app = create_app()
    routes = _api_routes(app)
    paths = app.openapi()["paths"]

    operaciones = {
        (method.upper(), path)
        for path, ops in paths.items()
        if path.startswith("/api/v1")
        for method in ops
        if method.upper() in _BUSINESS_METHODS
    }
    negocio = operaciones - _PUBLIC_ROUTES
    assert ("GET", COMPANIES) in negocio  # el endpoint de la matriz debe existir y estar protegido

    for method, path in negocio:
        route = routes.get((method, path))
        assert route is not None, f"{method} {path}: no se encontró la APIRoute"
        dependant = route.dependant  # type: ignore[attr-defined]
        if (method, path) in _OPEN_AUTHENTICATED:
            # Abierta a propósito: sin roles, pero DEBE exigir identidad.
            assert declared_roles(dependant) is None, f"{method} {path}: no debería declarar roles"
            assert requires_authentication(dependant), f"{method} {path}: no exige identidad"
        else:
            roles = declared_roles(dependant)
            assert roles, f"{method} {path}: ruta de negocio sin roles declarados (olvido)"

    # Refuerzo de comportamiento: la superficie de la matriz responde 401 sin token (401 > 403).
    client, dsns = authapi
    await _seed_ilex(dsns)
    resp = await client.get(COMPANIES, headers=host("ilex.localhost"))
    assert resp.status_code == 401
