"""Tests de comportamiento S1.4: registro con aprobación (spec docs/specs/S1.4).

Criterios C1-C14. `POST /register` es público en el subdominio y escribe (usuario pendiente +
empresa + membership) en el tenant del subdominio (contexto abierto desde `request.state.tenant`,
no desde un token). La aprobación es del `tenant_admin` (S1.6). Al registrarse se avisa (mock) solo
al admin, sin email al usuario final. Fase roja: `/register` y `/registrations` aún no existen.
"""

from __future__ import annotations

import re

import asyncpg
import httpx
import pytest

from tests._auth import USER_PASSWORD, USER_PASSWORD_HASH, bearer, host, login
from tests._companies import (
    INVALID_TAXID,
    VALID_CIF,
    VALID_CIF_2,
    admin_token,
    seed_admin,
    valid_nif,
)
from tests._dbtest import cif_blind_index_for, seed_company, seed_membership, seed_tenant, seed_user

Api = tuple[httpx.AsyncClient, dict[str, str]]

REGISTER = "/api/v1/register"
REGISTRATIONS = "/api/v1/registrations"


def _auth(token: str, hostname: str = "ilex.localhost") -> dict[str, str]:
    return {**host(hostname), **bearer(token)}


async def _register(
    client: httpx.AsyncClient,
    *,
    email: str,
    cif: str,
    company: str = "Empresa Nueva SL",
    password: str = USER_PASSWORD,
    hostname: str = "ilex.localhost",
) -> httpx.Response:
    """Alta autoservicio en el subdominio `hostname`."""
    body = {"email": email, "company_name": company, "cif": cif, "password": password}
    return await client.post(REGISTER, json=body, headers=host(hostname))


async def _user_row(dsns: dict[str, str], tenant_id: str, email: str) -> asyncpg.Record | None:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        return await conn.fetchrow(
            "SELECT id, status, role FROM users WHERE tenant_id = $1 AND email = $2",
            tenant_id,
            email,
        )
    finally:
        await conn.close()


# --- Registro -----------------------------------------------------------------------------------


async def test_c1_registro_valido_crea_usuario_pendiente(authapi: Api) -> None:
    """C1: registro válido -> usuario pendiente + empresa pendiente + membership (todo o nada)."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    resp = await _register(client, email="nuevo@correo.es", cif=VALID_CIF)
    assert resp.status_code in (201, 202)
    conn = await asyncpg.connect(dsns["admin"])
    try:
        user = await conn.fetchrow(
            "SELECT id, status, role FROM users WHERE tenant_id = $1 AND email = 'nuevo@correo.es'",
            tid,
        )
        company = await conn.fetchrow(
            "SELECT id, status FROM companies WHERE tenant_id = $1 AND cif_blind_index = $2",
            tid,
            cif_blind_index_for(tid, VALID_CIF),
        )
        members = await conn.fetchval(
            "SELECT count(*) FROM memberships WHERE user_id = $1 AND company_id = $2",
            user["id"],
            company["id"],
        )
    finally:
        await conn.close()
    assert user["status"] == "pending" and user["role"] == "user"
    assert company["status"] == "pending"
    assert members == 1


async def test_c2_cif_invalido_rechaza_el_registro(authapi: Api) -> None:
    """C2: CIF con dígito de control inválido -> 422, no se crea nada."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    resp = await _register(client, email="malo@correo.es", cif=INVALID_TAXID)
    assert resp.status_code == 422
    assert await _user_row(dsns, tid, "malo@correo.es") is None


async def test_c3_password_floja_rechaza_el_registro(authapi: Api) -> None:
    """C3: contraseña por debajo de la política -> 422, no se crea nada."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    resp = await _register(client, email="x@correo.es", cif=VALID_CIF, password="corta")
    assert resp.status_code == 422
    assert await _user_row(dsns, tid, "x@correo.es") is None


async def test_c4_email_duplicado_no_crea_duplicado(authapi: Api) -> None:
    """C4: email ya registrado -> respuesta genérica idéntica (anti-enumeración), sin duplicar."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    first = await _register(client, email="dup@correo.es", cif=VALID_CIF)
    assert first.status_code in (201, 202)
    second = await _register(client, email="dup@correo.es", cif=VALID_CIF_2, company="Otra")
    assert second.status_code == first.status_code  # misma respuesta, no revela existencia
    conn = await asyncpg.connect(dsns["admin"])
    try:
        count = await conn.fetchval(
            "SELECT count(*) FROM users WHERE tenant_id = $1 AND email = 'dup@correo.es'", tid
        )
    finally:
        await conn.close()
    assert count == 1


async def test_c5_cif_existente_vincula_a_la_empresa(authapi: Api) -> None:
    """C5 (1-A): si el CIF ya existe, el usuario se vincula a esa empresa; no se crea otra."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    existente = await seed_company(dsns["admin"], tenant_id=tid, name="Existente", cif=VALID_CIF)
    resp = await _register(client, email="empleado@correo.es", cif=VALID_CIF, company="da igual")
    assert resp.status_code in (201, 202)
    conn = await asyncpg.connect(dsns["admin"])
    try:
        companies = await conn.fetchval(
            "SELECT count(*) FROM companies WHERE tenant_id = $1 AND cif_blind_index = $2",
            tid,
            cif_blind_index_for(tid, VALID_CIF),
        )
        user = await conn.fetchrow(
            "SELECT id FROM users WHERE tenant_id = $1 AND email = 'empleado@correo.es'", tid
        )
        member = await conn.fetchval(
            "SELECT count(*) FROM memberships WHERE user_id = $1 AND company_id = $2",
            user["id"],
            existente,
        )
    finally:
        await conn.close()
    assert companies == 1  # no se crea otra empresa con ese CIF
    assert member == 1  # vinculado a la existente


async def test_c6_recien_registrado_no_puede_entrar(authapi: Api) -> None:
    """C6: un usuario recién registrado (pendiente) no puede hacer login -> 401."""
    client, dsns = authapi
    await seed_admin(dsns)
    resp = await _register(client, email="pend@correo.es", cif=VALID_CIF)
    assert resp.status_code in (201, 202)
    entrar = await login(client, "ilex.localhost", "pend@correo.es", USER_PASSWORD)
    assert entrar.status_code == 401


# --- Aprobación ---------------------------------------------------------------------------------


async def test_c7_admin_ve_los_registros_pendientes(authapi: Api) -> None:
    """C7: el `tenant_admin` lista los registros pendientes de su asesoría."""
    client, dsns = authapi
    await seed_admin(dsns)
    resp = await _register(client, email="nuevo@correo.es", cif=VALID_CIF)
    assert resp.status_code in (201, 202)
    token = await admin_token(client)
    lista = await client.get(REGISTRATIONS, headers=_auth(token))
    assert lista.status_code == 200
    assert "nuevo@correo.es" in [x["email"] for x in lista.json()]


async def test_m2_unirse_a_empresa_activa_se_marca_en_el_listado(authapi: Api) -> None:
    """M2: un registro cuyo CIF casa con una empresa ACTIVA existente se marca (secuestro por CIF).

    El que se une a una empresa ya activa aparece con `joins_existing_company`; el que crea empresa
    nueva (CIF nuevo, empresa pendiente), no. La pantalla de aprobación puede así advertirlo.
    """
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    await seed_company(dsns["admin"], tenant_id=tid, name="Existente", cif=VALID_CIF)  # active
    se_une = await _register(client, email="empleado@correo.es", cif=VALID_CIF)
    assert se_une.status_code in (201, 202)
    nueva = await _register(client, email="fundador@correo.es", cif=VALID_CIF_2, company="Nueva")
    assert nueva.status_code in (201, 202)
    token = await admin_token(client)
    lista = await client.get(REGISTRATIONS, headers=_auth(token))
    assert lista.status_code == 200
    by_email = {x["email"]: x for x in lista.json()}
    assert by_email["empleado@correo.es"]["joins_existing_company"] is True
    assert by_email["fundador@correo.es"]["joins_existing_company"] is False


async def test_c8_aprobar_activa_usuario_y_empresa(authapi: Api) -> None:
    """C8: aprobar activa al usuario y a su empresa; a partir de ahí sí puede entrar (2-B)."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    resp = await _register(client, email="nuevo@correo.es", cif=VALID_CIF)
    assert resp.status_code in (201, 202)
    user = await _user_row(dsns, tid, "nuevo@correo.es")
    token = await admin_token(client)
    aprob = await client.post(f"{REGISTRATIONS}/{user['id']}/approve", headers=_auth(token))
    assert aprob.status_code == 200
    conn = await asyncpg.connect(dsns["admin"])
    try:
        user_status = await conn.fetchval("SELECT status FROM users WHERE id = $1", user["id"])
        company_status = await conn.fetchval(
            "SELECT status FROM companies WHERE tenant_id = $1 AND cif_blind_index = $2",
            tid,
            cif_blind_index_for(tid, VALID_CIF),
        )
    finally:
        await conn.close()
    assert user_status == "active" and company_status == "active"
    entrar = await login(client, "ilex.localhost", "nuevo@correo.es", USER_PASSWORD)
    assert entrar.status_code == 200


async def test_c9_rechazar_descarta_el_registro(authapi: Api) -> None:
    """C9: rechazar elimina al usuario pendiente y a su empresa huérfana; no puede entrar."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    resp = await _register(client, email="nuevo@correo.es", cif=VALID_CIF)
    assert resp.status_code in (201, 202)
    user = await _user_row(dsns, tid, "nuevo@correo.es")
    token = await admin_token(client)
    rechazo = await client.post(f"{REGISTRATIONS}/{user['id']}/reject", headers=_auth(token))
    assert rechazo.status_code in (200, 204)
    assert await _user_row(dsns, tid, "nuevo@correo.es") is None
    conn = await asyncpg.connect(dsns["admin"])
    try:
        companies = await conn.fetchval(
            "SELECT count(*) FROM companies WHERE tenant_id = $1 AND cif_blind_index = $2",
            tid,
            cif_blind_index_for(tid, VALID_CIF),
        )
    finally:
        await conn.close()
    assert companies == 0  # empresa del registro, huérfana -> eliminada


async def test_c10_solo_tenant_admin_gestiona_registros(authapi: Api) -> None:
    """C10: un `user` (no admin) no puede gestionar registros -> 403 (portero)."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    company = await seed_company(dsns["admin"], tenant_id=tid, name="Co", cif=VALID_CIF_2)
    emp = await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="emp@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    await seed_membership(dsns["admin"], user_id=emp, company_id=company, tenant_id=tid)
    token = await admin_token(client, email="emp@ilex.es")
    lista = await client.get(REGISTRATIONS, headers=_auth(token))
    assert lista.status_code == 403


async def test_c11_gestion_acotada_a_la_asesoria(authapi: Api) -> None:
    """C11: aprobar por id un registro de otra asesoría -> 404 (RLS)."""
    client, dsns = authapi
    await seed_admin(dsns, slug="ilex")
    tid_otra, _ = await seed_admin(dsns, slug="otra", email="admin@otra.es")
    resp = await _register(
        client, email="dotra@correo.es", cif=VALID_CIF, hostname="otra.localhost"
    )
    assert resp.status_code in (201, 202)
    de_otra = await _user_row(dsns, tid_otra, "dotra@correo.es")
    token_ilex = await admin_token(client)
    aprob = await client.post(f"{REGISTRATIONS}/{de_otra['id']}/approve", headers=_auth(token_ilex))
    assert aprob.status_code == 404


# --- Notificación (mock), trazabilidad y anti-abuso ---------------------------------------------


async def test_c12_al_registrarse_avisa_al_admin_y_pide_verificar_el_email_al_registrante(
    authapi: Api,
) -> None:
    """C12 + bloque 2: se avisa al admin (pendiente de aprobación) Y al registrante (verificación de
    su email) -- pero a NADIE más, y el mensaje al registrante no es una aprobación."""
    from notifications import get_notifier  # seam del backend mock (aún no existe -> rojo)

    client, dsns = authapi
    await seed_admin(dsns)  # admin@ilex.es
    get_notifier().reset()
    resp = await _register(client, email="nuevo@correo.es", cif=VALID_CIF)
    assert resp.status_code in (201, 202)
    mensajes = {m.to: m for m in get_notifier().messages}
    assert set(mensajes) == {"admin@ilex.es", "nuevo@correo.es"}
    assert mensajes["admin@ilex.es"].kind == "registration_pending"
    assert mensajes["nuevo@correo.es"].kind == "email_verification"
    # El mensaje al registrante pide confirmar el email, nunca da por aprobada la solicitud.
    cuerpo_registrante = mensajes["nuevo@correo.es"].body.lower()
    assert "confirma" in cuerpo_registrante
    assert "aprobad" not in cuerpo_registrante  # ni "aprobado" ni "aprobada"


async def test_c13_registro_y_aprobacion_dejan_rastro_en_audit(authapi: Api) -> None:
    """C13: registro y aprobación escriben en audit_log (`user.register`, `user.approve`)."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    resp = await _register(client, email="nuevo@correo.es", cif=VALID_CIF)
    assert resp.status_code in (201, 202)
    user = await _user_row(dsns, tid, "nuevo@correo.es")
    token = await admin_token(client)
    aprob = await client.post(f"{REGISTRATIONS}/{user['id']}/approve", headers=_auth(token))
    assert aprob.status_code == 200
    conn = await asyncpg.connect(dsns["admin"])
    try:
        acciones = {
            r["action"]
            for r in await conn.fetch("SELECT action FROM audit_log WHERE tenant_id = $1", tid)
        }
    finally:
        await conn.close()
    assert "user.register" in acciones
    assert "user.approve" in acciones


async def test_c14_registro_limitado_por_ip(authapi: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    """C14: el registro está limitado por IP (anti-spam) -> 429 al superar el tope."""
    from shared import config

    client, dsns = authapi
    await seed_admin(dsns)
    monkeypatch.setenv("REGISTER_MAX_PER_IP", "3")
    config.get_settings.cache_clear()

    for i in range(3):
        resp = await _register(client, email=f"u{i}@correo.es", cif=valid_nif(20_000_000 + i))
        assert resp.status_code in (201, 202)
    extra = await _register(client, email="otromas@correo.es", cif=valid_nif(20_000_099))
    assert extra.status_code == 429

    config.get_settings.cache_clear()


# --- Verificación del email del registrante (bloque 2, PROMPT-AUTOFACTU-AUTH-COMPLETO) ----------

VERIFY_EMAIL = "/api/v1/auth/register/verify-email"


def _verification_token_from(body: str) -> str:
    match = re.search(r"registro/confirmar\?token=([^\s]+)", body)
    assert match, f"no se encontró un enlace de verificación en: {body!r}"
    return match.group(1)


async def test_verify_email_marca_el_registro_como_verificado_sin_aprobarlo(authapi: Api) -> None:
    from notifications import get_notifier

    client, dsns = authapi
    await seed_admin(dsns)
    get_notifier().reset()
    resp = await _register(client, email="nuevo@correo.es", cif=VALID_CIF)
    assert resp.status_code in (201, 202)
    mensaje = next(m for m in get_notifier().messages if m.to == "nuevo@correo.es")
    token = _verification_token_from(mensaje.body)

    verificar = await client.post(
        VERIFY_EMAIL, json={"token": token}, headers=host("ilex.localhost")
    )
    assert verificar.status_code == 200

    admin = await admin_token(client)
    lista = await client.get(REGISTRATIONS, headers=_auth(admin))
    entrada = next(x for x in lista.json() if x["email"] == "nuevo@correo.es")
    assert entrada["email_verified"] is True
    assert entrada["id"]  # sigue pendiente de aprobación: no ha desaparecido del listado


async def test_registro_sin_verificar_el_email_sigue_aprobable(authapi: Api) -> None:
    """La verificación informa, no bloquea: el admin puede aprobar sin que nadie confirme nada."""
    client, dsns = authapi
    await seed_admin(dsns)
    resp = await _register(client, email="nuevo@correo.es", cif=VALID_CIF)
    assert resp.status_code in (201, 202)
    admin = await admin_token(client)
    lista = await client.get(REGISTRATIONS, headers=_auth(admin))
    entrada = next(x for x in lista.json() if x["email"] == "nuevo@correo.es")
    assert entrada["email_verified"] is False

    aprob = await client.post(f"{REGISTRATIONS}/{entrada['id']}/approve", headers=_auth(admin))
    assert aprob.status_code == 200


async def test_verify_email_token_desconocido_da_401(authapi: Api) -> None:
    client, dsns = authapi
    await seed_admin(dsns)
    resp = await client.post(
        VERIFY_EMAIL, json={"token": "no-es-un-token-real"}, headers=host("ilex.localhost")
    )
    assert resp.status_code == 401


async def test_verify_email_consume_el_token_de_un_solo_uso(authapi: Api) -> None:
    from notifications import get_notifier

    client, dsns = authapi
    await seed_admin(dsns)
    get_notifier().reset()
    await _register(client, email="nuevo@correo.es", cif=VALID_CIF)
    mensaje = next(m for m in get_notifier().messages if m.to == "nuevo@correo.es")
    token = _verification_token_from(mensaje.body)

    primero = await client.post(VERIFY_EMAIL, json={"token": token}, headers=host("ilex.localhost"))
    assert primero.status_code == 200
    reuso = await client.post(VERIFY_EMAIL, json={"token": token}, headers=host("ilex.localhost"))
    assert reuso.status_code == 401


async def test_verify_email_de_otro_tenant_da_401(authapi: Api) -> None:
    """F2: un token de verificación sembrado en un tenant no vale desde el subdominio de otro."""
    from notifications import get_notifier

    client, dsns = authapi
    await seed_admin(dsns)  # ilex
    await seed_tenant(dsns["admin"], "otra", "Otra Asesoría SL")
    get_notifier().reset()
    await _register(client, email="nuevo@correo.es", cif=VALID_CIF)
    mensaje = next(m for m in get_notifier().messages if m.to == "nuevo@correo.es")
    token = _verification_token_from(mensaje.body)

    cruzado = await client.post(VERIFY_EMAIL, json={"token": token}, headers=host("otra.localhost"))
    assert cruzado.status_code == 401
