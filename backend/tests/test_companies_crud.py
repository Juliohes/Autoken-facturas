"""Tests de comportamiento S1.5: CRUD de empresas + trazabilidad (spec docs/specs/S1.5).

Criterios C1-C8, C13, C14. Observable vía HTTP (cliente ASGI con `Host` de tenant) contra Postgres
real + Redis, autenticado como `tenant_admin` (portero de S1.6). Fase roja: los endpoints
POST/PATCH/DELETE de `/companies` aún no existen (solo el GET de S1.6).
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
import httpx
import pytest

from tests._auth import USER_PASSWORD_HASH, bearer, host
from tests._companies import (
    COMPANIES,
    INVALID_TAXID,
    VALID_CIF,
    VALID_CIF_2,
    VALID_NIF,
    admin_token,
    seed_admin,
)
from tests._dbtest import seed_company, seed_membership, seed_user

Api = tuple[httpx.AsyncClient, dict[str, str]]


def _auth(token: str, hostname: str = "ilex.localhost") -> dict[str, str]:
    return {**host(hostname), **bearer(token)}


async def test_c1_crear_empresa_valida(authapi: Api) -> None:
    """C1: crear una empresa con CIF válido -> 201, status active, aparece en la lista."""
    client, dsns = authapi
    await seed_admin(dsns)
    token = await admin_token(client)
    resp = await client.post(
        COMPANIES, json={"name": "Nueva SL", "cif": VALID_CIF}, headers=_auth(token)
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "active"
    assert body["cif"] == VALID_CIF
    lista = await client.get(COMPANIES, headers=_auth(token))
    assert any(c["cif"] == VALID_CIF for c in lista.json())


async def test_c2_cif_invalido_se_rechaza(authapi: Api) -> None:
    """C2: CIF con dígito de control inválido -> 422, no se crea (nunca un registro a medias)."""
    client, dsns = authapi
    await seed_admin(dsns)
    token = await admin_token(client)
    resp = await client.post(
        COMPANIES, json={"name": "Mala", "cif": INVALID_TAXID}, headers=_auth(token)
    )
    assert resp.status_code == 422
    lista = await client.get(COMPANIES, headers=_auth(token))
    assert lista.json() == []


async def test_c3_cif_duplicado_en_la_asesoria(authapi: Api) -> None:
    """C3: CIF ya existente en la asesoría -> 409; el mismo CIF en otra asesoría sí se permite."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    await seed_company(dsns["admin"], tenant_id=tid, name="Existente", cif=VALID_CIF)
    token = await admin_token(client)
    dup = await client.post(
        COMPANIES, json={"name": "Otra", "cif": VALID_CIF}, headers=_auth(token)
    )
    assert dup.status_code == 409

    await seed_admin(dsns, slug="otra", email="admin@otra.es")
    token_otra = await admin_token(client, email="admin@otra.es", hostname="otra.localhost")
    cross = await client.post(
        COMPANIES,
        json={"name": "Distinta", "cif": VALID_CIF},
        headers=_auth(token_otra, "otra.localhost"),
    )
    assert cross.status_code == 201  # mismo CIF en otra asesoría = empresa distinta


async def test_c4_user_no_puede_gestionar_empresas(authapi: Api) -> None:
    """C4: un `user` (empleado) no gestiona empresas -> 403 (portero: gestión = tenant_admin)."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    company = await seed_company(dsns["admin"], tenant_id=tid, name="EmpleadoCo", cif=VALID_CIF_2)
    emp = await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="emp@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    await seed_membership(dsns["admin"], user_id=emp, company_id=company, tenant_id=tid)
    token = await admin_token(client, email="emp@ilex.es")
    resp = await client.post(COMPANIES, json={"name": "X", "cif": VALID_CIF}, headers=_auth(token))
    assert resp.status_code == 403


async def test_c5_editar_y_activar_una_pendiente(authapi: Api) -> None:
    """C5: editar una empresa y activar una `pending` (status pending -> active)."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    cid = await seed_company(
        dsns["admin"], tenant_id=tid, name="Pend", cif=VALID_CIF, status="pending"
    )
    token = await admin_token(client)
    resp = await client.patch(
        f"{COMPANIES}/{cid}", json={"status": "active", "notes": "revisada"}, headers=_auth(token)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


async def test_c6_editar_cif_revalida_y_respeta_unicidad(authapi: Api) -> None:
    """C6: editar el CIF a inválido -> 422; a uno duplicado -> 409; a uno válido y libre -> 200."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    await seed_company(dsns["admin"], tenant_id=tid, name="A", cif=VALID_CIF)
    cid = await seed_company(dsns["admin"], tenant_id=tid, name="B", cif=VALID_CIF_2)
    token = await admin_token(client)
    invalido = await client.patch(
        f"{COMPANIES}/{cid}", json={"cif": INVALID_TAXID}, headers=_auth(token)
    )
    assert invalido.status_code == 422
    duplicado = await client.patch(
        f"{COMPANIES}/{cid}", json={"cif": VALID_CIF}, headers=_auth(token)
    )
    assert duplicado.status_code == 409
    valido = await client.patch(f"{COMPANIES}/{cid}", json={"cif": VALID_NIF}, headers=_auth(token))
    assert valido.status_code == 200


async def test_c7_borrar_empresa_sin_dependencias(authapi: Api) -> None:
    """C7: borrar una empresa sin usuarios ni facturas -> 204; desaparece de la lista."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    cid = await seed_company(dsns["admin"], tenant_id=tid, name="Borrable", cif=VALID_CIF)
    token = await admin_token(client)
    resp = await client.delete(f"{COMPANIES}/{cid}", headers=_auth(token))
    assert resp.status_code == 204
    lista = await client.get(COMPANIES, headers=_auth(token))
    assert all(c["cif"] != VALID_CIF for c in lista.json())


async def test_c8_no_borrar_empresa_con_usuarios(authapi: Api) -> None:
    """C8: borrar una empresa con usuarios (memberships) -> 409, no se borra."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    cid = await seed_company(dsns["admin"], tenant_id=tid, name="ConUsers", cif=VALID_CIF)
    emp = await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="e@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    await seed_membership(dsns["admin"], user_id=emp, company_id=cid, tenant_id=tid)
    token = await admin_token(client)
    resp = await client.delete(f"{COMPANIES}/{cid}", headers=_auth(token))
    assert resp.status_code == 409


async def test_c13_gestion_acotada_a_la_asesoria(authapi: Api) -> None:
    """C13: editar/borrar por id una empresa de otra asesoría -> 404 (no existe en su contexto)."""
    client, dsns = authapi
    await seed_admin(dsns, slug="ilex")
    tid_otra, _ = await seed_admin(dsns, slug="otra", email="admin@otra.es")
    de_otra = await seed_company(dsns["admin"], tenant_id=tid_otra, name="DeOtra", cif=VALID_CIF)
    token_ilex = await admin_token(client)
    borrar = await client.delete(f"{COMPANIES}/{de_otra}", headers=_auth(token_ilex))
    assert borrar.status_code == 404
    editar = await client.patch(
        f"{COMPANIES}/{de_otra}", json={"name": "hack"}, headers=_auth(token_ilex)
    )
    assert editar.status_code == 404


async def test_c14_toda_mutacion_deja_rastro_en_audit_log(authapi: Api) -> None:
    """C14: crear y borrar una empresa escriben entradas en audit_log (actor/acción/entidad/id)."""
    client, dsns = authapi
    tid, admin_id = await seed_admin(dsns)
    borrable = await seed_company(dsns["admin"], tenant_id=tid, name="Del", cif=VALID_CIF_2)
    token = await admin_token(client)
    creada = await client.post(
        COMPANIES, json={"name": "Aud", "cif": VALID_CIF}, headers=_auth(token)
    )
    assert creada.status_code == 201
    borrada = await client.delete(f"{COMPANIES}/{borrable}", headers=_auth(token))
    assert borrada.status_code == 204

    conn = await asyncpg.connect(dsns["admin"])
    try:
        filas = await conn.fetch(
            "SELECT action, entity, actor_id FROM audit_log WHERE tenant_id = $1", tid
        )
    finally:
        await conn.close()
    acciones = {f["action"] for f in filas}
    assert "company.create" in acciones
    assert "company.delete" in acciones
    assert all(f["entity"] == "company" for f in filas)
    assert all(str(f["actor_id"]) == str(admin_id) for f in filas)


async def test_m2_carrera_en_unique_se_traduce_a_conflicto(
    authapi: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M2: si el pre-check no ve el duplicado (carrera), el UNIQUE se traduce a conflicto (409).

    Determinista: se saltea el pre-check `cif_exists` a nivel de repositorio para forzar el camino
    de captura de la `IntegrityError` del UNIQUE `(tenant_id, cif)`, sin simular concurrencia real.
    """
    from companies import repository, service
    from shared.db import tenant_session

    _, dsns = authapi
    tid, admin_id = await seed_admin(dsns)
    await seed_company(dsns["admin"], tenant_id=tid, name="Existente", cif=VALID_CIF)

    async def _pre_check_ciego(*args: object, **kwargs: object) -> bool:
        return False  # simula la carrera: el pre-check no ve el duplicado ya presente

    monkeypatch.setattr(repository, "cif_exists", _pre_check_ciego)

    with pytest.raises(service.DuplicateCif):
        async with tenant_session(UUID(tid)) as session:
            await service.create_company(
                session, actor_id=UUID(admin_id), name="Otra", cif=VALID_CIF, notes=None
            )
