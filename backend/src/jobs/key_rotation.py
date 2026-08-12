"""Rotación de la clave maestra de cifrado en reposo (S5.2 C9, spec docs/specs/S5.2 §2/§7).

Re-cifra, tenant a tenant, todo lo que vive cifrado con la clave maestra VIEJA usando la clave
maestra NUEVA (`companies`/`counterparties`.cif/name, `invoices`.counterparty_tax_id/
counterparty_name + su índice ciego, `ocr_extractions`.counterparty_tax_id/counterparty_name, y
`invoice_edits`.old_value/new_value cuando el campo es sensible). Nunca se guarda ninguna clave: la
vieja y la nueva llegan como parámetros explícitos (env vars / CLI, nunca hardcodeadas) y solo viven
en memoria mientras dura la rotación.

**Reanudable por tenant** (spec §5, "reanudable sin duplicar trabajo"): cada tenant se rota en SU
PROPIA transacción (`shared.db.tenant_session`, `begin()` implícito) — si el proceso se interrumpe a
mitad, los tenants ya confirmados quedan del todo rotados y los pendientes del todo con la clave
vieja, nunca una mezcla a medias dentro de un tenant. Al reanudar, `_is_already_rotated` prueba a
descifrar con la clave NUEVA una fila de CADA tabla cifrada (no solo `companies`) y solo entonces la
salta.

**Escritura concurrente durante la rotación (hallazgo de auditoría de seguridad/arquitectura)**: la
app puede seguir sirviendo tráfico con la clave VIEJA mientras este script corre (aún no se ha
reiniciado con la clave nueva). Dos mitigaciones, ninguna suficiente por sí sola:
1. `_rotate_table` bloquea las filas leídas con `SELECT ... FOR UPDATE` dentro de la misma
   transacción: una escritura concurrente de la app sobre una fila YA seleccionada por la rotación
   espera a que la transacción de rotación termine (evita perder esa escritura). `invoice_edits`
   es la única excepción (ver docstring de `_rotate_invoice_edits`): es append-only por diseño y
   solo tiene concedido `UPDATE` acotado a `old_value`/`new_value` (migración 0021), que no permite
   `FOR UPDATE` (exige `UPDATE` de la fila completa en Postgres).
2. Esto NO cubre una fila `INSERT`ada por la app DESPUÉS del `SELECT` de su tabla y ANTES del commit
   de la rotación (no estaba en el conjunto bloqueado). Por eso el runbook
   (`docs/runbooks/rotacion-clave-cifrado.md`) exige una ventana sin escritura (parar la app o
   ponerla en mantenimiento) durante la rotación de cada tenant, no solo confiar en el bloqueo de
   filas.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from invoicing.repository import SENSITIVE_EDIT_FIELDS
from platform_admin.repository import list_tenants
from shared.db import platform_session, tenant_session
from shared.encryption import ENCRYPTED_COLUMNS, blind_index, derive_tenant_encryption_key
from shared.tax_id import normalize_tax_id

logger = structlog.get_logger("jobs.key_rotation")

__all__ = ["RotationSummary", "rotate_all_tenants"]


@dataclass(frozen=True)
class RotationSummary:
    """Resultado de rotar todos los tenants: cuántos se rotaron de verdad, cuántos ya lo estaban
    (reanudación) y cuántos no tenían nada que rotar (tenant sin empresas)."""

    tenants_total: int
    rotated: int
    already_done: int
    empty: int


async def _is_tenant_empty(session: AsyncSession) -> bool:
    """True si el tenant no tiene ninguna empresa (nada que rotar: la integridad referencial
    garantiza que `counterparties`/`invoices`/`ocr_extractions` tampoco tienen filas suyas)."""
    row = (await session.execute(text("SELECT 1 FROM companies LIMIT 1"))).first()
    return row is None


async def _decrypts_with(session: AsyncSession, table: str, column: str, key: str) -> bool | None:
    """¿La primera fila de `table` descifra `column` con `key`? `None` si la tabla no tiene filas
    (nada que decidir para esa tabla). Usa un `SAVEPOINT`: un intento de descifrado con la clave
    equivocada lanza un error de Postgres que abortaría el resto de la transacción sin él.

    El valor a probar se liga como parámetro (`:value`), nunca interpolado: la segunda consulta no
    vuelve a nombrar la tabla/columna (evita repetir el `SELECT ... FROM` y, con él, el riesgo de
    escribirlo sin la cláusula `FROM`, un bug real que este módulo tuvo durante su desarrollo).
    """
    query = f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL LIMIT 1"  # noqa: S608
    row = (await session.execute(text(query))).first()
    if row is None:
        return None
    try:
        async with session.begin_nested():
            await session.execute(
                text("SELECT pgp_sym_decrypt(:value, :key)"),
                {"value": row[0], "key": key},
            )
        return True
    except Exception:  # noqa: BLE001 - cualquier fallo de descifrado significa "no es esta clave"
        return False


async def _is_already_rotated(session: AsyncSession, new_master: str, tenant_id: UUID) -> bool:
    """¿Ya está este tenant cifrado con la clave NUEVA? Prueba una fila de CADA tabla cifrada (no
    solo `companies`, a diferencia de una primera versión de este chequeo): si cualquiera de ellas
    tiene una fila que NO descifra con la clave nueva, el tenant no está del todo rotado todavía.
    Una tabla sin filas no aporta información y se ignora (spec §5: nunca se decide "ya rotado" por
    una tabla vacía cuando otra con datos podría no estarlo)."""
    new_key = derive_tenant_encryption_key(new_master, str(tenant_id))
    for table, columns in ENCRYPTED_COLUMNS.items():
        for column in columns:
            result = await _decrypts_with(session, table, column, new_key)
            if result is False:
                return False
    return True


async def _rotate_table(
    session: AsyncSession,
    table: str,
    columns: dict[str, bool],
    *,
    old_master: str,
    new_master: str,
    tenant_id: UUID,
) -> None:
    """Re-cifra todas las filas de `table` visibles en el contexto (RLS ya acota al tenant).

    Mismo patrón fila-a-fila que el backfill de la migración 0020: se lee descifrado con la clave
    VIEJA, se recalcula el índice ciego (si aplica) y se vuelve a escribir cifrado con la clave
    NUEVA, todo en la misma sentencia `UPDATE` por fila. `FOR UPDATE` bloquea las filas leídas hasta
    el commit de esta transacción (ver docstring del módulo, mitigación 1 de la carrera con
    escritura concurrente).
    """
    old_key = derive_tenant_encryption_key(old_master, str(tenant_id))
    new_key = derive_tenant_encryption_key(new_master, str(tenant_id))
    col_list = ", ".join(f"pgp_sym_decrypt({c}, :old_key)::text AS {c}" for c in columns)
    rows = (
        (
            await session.execute(
                text(f"SELECT id, {col_list} FROM {table} FOR UPDATE"),  # noqa: S608
                {"old_key": old_key},
            )
        )
        .mappings()
        .all()
    )
    for row in rows:
        set_clauses = []
        params: dict[str, object] = {"id": row["id"], "new_key": new_key}
        for column, has_index in columns.items():
            value = row[column]
            set_clauses.append(f"{column} = pgp_sym_encrypt(:{column}, :new_key)")
            params[column] = value
            if has_index:
                # Normalizado SIEMPRE antes del índice ciego (igual que la aplicación en caliente,
                # `shared.tax_id.normalize_tax_id`): `companies`/`counterparties` ya guardan el CIF
                # canónico, pero `invoices.counterparty_tax_id` puede llevar el valor tal cual lo
                # tecleó un humano — sin este paso, el índice recalculado aquí no coincidiría con el
                # que espera el filtro exacto de CIF del panel (C5), en silencio (hallazgo de
                # auditoría SOLID).
                idx = (
                    blind_index(new_master, str(tenant_id), normalize_tax_id(value))
                    if value
                    else None
                )
                set_clauses.append(f"{column}_blind_index = :{column}_idx")
                params[f"{column}_idx"] = idx
        await session.execute(
            text(f"UPDATE {table} SET {', '.join(set_clauses)} WHERE id = :id"),  # noqa: S608
            params,
        )


async def _rotate_invoice_edits(
    session: AsyncSession, *, old_master: str, new_master: str, tenant_id: UUID
) -> None:
    """Re-cifra `invoice_edits.old_value`/`new_value` de las filas con un campo sensible (S5.2 C7).

    Formato `encode(pgp_sym_encrypt(valor, clave), 'base64')` guardado en la columna TEXT
    existente (mismo patrón que `invoicing.repository.insert_edits`): se descifra con la clave
    vieja, se vuelve a codificar con la nueva.

    SIN `FOR UPDATE` a propósito, a diferencia de `_rotate_table`: `invoice_edits` es append-only
    (migración 0008, `SELECT, INSERT` únicamente) y la migración 0021 solo concede `UPDATE` acotado
    a las columnas `old_value`/`new_value` (el resto de la fila sigue siendo inmutable de verdad) —
    un `SELECT ... FOR UPDATE` exige `UPDATE` de la fila COMPLETA en Postgres, no basta un grant por
    columnas, y fallaría con `InsufficientPrivilegeError` (hallazgo real durante las pruebas de esta
    tarea). El bloqueo de fila se sacrifica aquí; el resto de la mitigación de la carrera con
    escritura concurrente (ventana sin tráfico, ver runbook) sigue aplicando igual.
    """
    old_key = derive_tenant_encryption_key(old_master, str(tenant_id))
    new_key = derive_tenant_encryption_key(new_master, str(tenant_id))
    sensitive = ", ".join(f"'{field}'" for field in SENSITIVE_EDIT_FIELDS)
    rows = (
        (
            await session.execute(
                text(
                    f"SELECT id, "  # noqa: S608
                    f"pgp_sym_decrypt(decode(old_value, 'base64'), :old_key)::text AS old_value, "
                    f"pgp_sym_decrypt(decode(new_value, 'base64'), :old_key)::text AS new_value "
                    f"FROM invoice_edits WHERE field IN ({sensitive})"
                ),
                {"old_key": old_key},
            )
        )
        .mappings()
        .all()
    )
    for row in rows:
        await session.execute(
            text(
                "UPDATE invoice_edits SET "
                "old_value = encode(pgp_sym_encrypt(:old_value, :new_key), 'base64'), "
                "new_value = encode(pgp_sym_encrypt(:new_value, :new_key), 'base64') "
                "WHERE id = :id"
            ),
            {
                "id": row["id"],
                "old_value": row["old_value"],
                "new_value": row["new_value"],
                "new_key": new_key,
            },
        )


async def rotate_tenant(tenant_id: UUID, *, old_master: str, new_master: str) -> str:
    """Rota la clave de UN tenant, en su propia transacción (atómico: todo o nada).

    Devuelve `"rotated"`, `"already_done"` (reanudación) o `"empty"` (tenant sin empresas, nada que
    rotar).
    """
    async with tenant_session(tenant_id) as session:
        if await _is_tenant_empty(session):
            return "empty"
        if await _is_already_rotated(session, new_master, tenant_id):
            return "already_done"
        for table, columns in ENCRYPTED_COLUMNS.items():
            await _rotate_table(
                session,
                table,
                columns,
                old_master=old_master,
                new_master=new_master,
                tenant_id=tenant_id,
            )
        await _rotate_invoice_edits(
            session, old_master=old_master, new_master=new_master, tenant_id=tenant_id
        )
        return "rotated"


async def rotate_all_tenants(*, old_master: str, new_master: str) -> RotationSummary:
    """Rota TODOS los tenants, uno a uno. Un fallo en un tenant no aborta el resto (se registra y
    se continúa): la rotación de los demás tenants es independiente."""
    async with platform_session() as session:
        tenants = await list_tenants(session)

    rotated = already_done = empty = 0
    for tenant in tenants:
        try:
            outcome = await rotate_tenant(tenant.id, old_master=old_master, new_master=new_master)
        except Exception:
            logger.exception("key_rotation.tenant_failed", tenant_id=str(tenant.id))
            continue
        if outcome == "rotated":
            rotated += 1
        elif outcome == "already_done":
            already_done += 1
        else:
            empty += 1
        logger.info("key_rotation.tenant_done", tenant_id=str(tenant.id), outcome=outcome)

    return RotationSummary(
        tenants_total=len(tenants), rotated=rotated, already_done=already_done, empty=empty
    )
