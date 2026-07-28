"""Tests de comportamiento de la migración 0023: alta/baja de cuentas sembradas (sin autoservicio).

Cierra el hueco de `identity/activation.py` ("en producción emite un script de plataforma" que
nunca se versionó): antes de esta tarea, un `platform_admin` o un `tenant_admin`/`user` sembrado
directamente se creaba con un INSERT SQL suelto contra la BD real. Estas funciones (`provision_
platform_admin`/`provision_tenant_account`/`revoke_platform_admin`, SECURITY DEFINER) son el único
camino legítimo — el mismo que consume `scripts/create_account.py`.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError

from identity import repository
from tests._dbtest import seed_tenant

Api = tuple[httpx.AsyncClient, dict[str, str]]


async def test_alta_de_platform_admin_queda_pendiente_de_activacion(authapi: Api) -> None:
    _client, _dsns = authapi
    identity = await repository.create_platform_admin_account("nuevo-tech@autoken.es")
    assert identity.email == "nuevo-tech@autoken.es"
    assert identity.role == "platform_admin"
    assert identity.is_admin_tech is False


async def test_alta_de_platform_admin_admite_el_flag_admin_tech(authapi: Api) -> None:
    _client, _dsns = authapi
    identity = await repository.create_platform_admin_account(
        "tech2@autoken.es", is_admin_tech=True
    )
    assert identity.is_admin_tech is True


async def test_email_de_platform_admin_duplicado_falla(authapi: Api) -> None:
    _client, _dsns = authapi
    await repository.create_platform_admin_account("dup@autoken.es")
    with pytest.raises(IntegrityError):
        await repository.create_platform_admin_account("dup@autoken.es")


async def test_alta_de_tenant_admin_en_un_tenant_concreto(authapi: Api) -> None:
    _client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "setex", "Setex")
    identity = await repository.create_tenant_account(tenant_id, "julio@setex.test", "tenant_admin")
    assert identity.role == "tenant_admin"
    assert identity.email == "julio@setex.test"


async def test_alta_de_user_normal_en_un_tenant_concreto(authapi: Api) -> None:
    _client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    identity = await repository.create_tenant_account(tenant_id, "prueba@ilex.test", "user")
    assert identity.role == "user"


async def test_alta_de_tenant_account_rechaza_role_platform_admin(authapi: Api) -> None:
    """El camino de alta de plataforma es otra función; esta rechaza explícitamente ese rol."""
    _client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "setex", "Setex")
    with pytest.raises(DBAPIError):
        await repository.create_tenant_account(tenant_id, "x@setex.test", "platform_admin")


async def test_mismo_email_convive_como_platform_admin_y_como_cuenta_de_tenant(
    authapi: Api,
) -> None:
    """Unicidad de email por tenant (0001) + índice parcial de plataforma (0003): espacios
    distintos, el mismo email puede tener una cuenta de plataforma y otra de tenant a la vez."""
    _client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    await repository.create_platform_admin_account("soporte@autoken.es")
    identity = await repository.create_tenant_account(tenant_id, "soporte@autoken.es", "user")
    assert identity.role == "user"


async def test_revocar_un_platform_admin_existente_lo_borra(authapi: Api) -> None:
    _client, _dsns = authapi
    await repository.create_platform_admin_account("baja@autoken.es")
    revoked_id = await repository.revoke_platform_admin_account("baja@autoken.es")
    assert revoked_id is not None
    # Vuelve a poder darse de alta: la fila anterior ya no existe (índice único liberado).
    identity = await repository.create_platform_admin_account("baja@autoken.es")
    assert identity.email == "baja@autoken.es"


async def test_revocar_un_email_inexistente_devuelve_none(authapi: Api) -> None:
    _client, _dsns = authapi
    assert await repository.revoke_platform_admin_account("no-existe@autoken.es") is None


async def test_find_platform_admin_for_reissue_cuenta_inexistente(authapi: Api) -> None:
    _client, _dsns = authapi
    assert await repository.find_platform_admin_for_reissue("no-existe@autoken.es") is None


async def test_find_platform_admin_for_reissue_pendiente_de_activar(authapi: Api) -> None:
    """Token perdido de una cuenta que aún no completó su activación: reemitible."""
    _client, _dsns = authapi
    identity = await repository.create_platform_admin_account("pendiente@autoken.es")
    found = await repository.find_platform_admin_for_reissue("pendiente@autoken.es")
    assert found == (identity.id, False)


async def test_find_platform_admin_for_reissue_ya_activada(authapi: Api) -> None:
    """Una cuenta que ya fijó su contraseña no es un token perdido: es contraseña olvidada."""
    _client, dsns = authapi
    from tests._dbtest import seed_user

    uid = await seed_user(
        dsns["admin"],
        tenant_id=None,
        email="ya-activo@autoken.es",
        role="platform_admin",
        password_hash="argon2-hash-de-mentira",
    )
    found = await repository.find_platform_admin_for_reissue("ya-activo@autoken.es")
    assert found == (uid, True)


async def test_revocar_no_toca_cuentas_de_tenant_con_el_mismo_email(authapi: Api) -> None:
    """`revoke_platform_admin` está acotado a `tenant_id IS NULL`: nunca borra una cuenta de
    tenant homónima (invariante de la propia función SQL, no solo del repositorio)."""
    _client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "setex", "Setex")
    await repository.create_tenant_account(tenant_id, "compartido@setex.test", "user")
    assert await repository.revoke_platform_admin_account("compartido@setex.test") is None
