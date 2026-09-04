"""Helper de escritura del registro de auditoría (`audit_log`), adelanto de S1.8 (decisión Julio).

Cada mutación de dominio deja una fila **append-only** en `audit_log`, dentro del MISMO contexto de
tenant de la petición: el `tenant_id` de la fila se toma de la variable de sesión `app.tenant_id`
que fijó `tenant_session` (S1.1), de modo que la política RLS `WITH CHECK` la acepta y la entrada no
puede escribirse en otro tenant. La tabla es append-only por grants (el rol runtime solo tiene
SELECT/INSERT; UPDATE/DELETE revocados), garantizado en la migración 0001.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# El `tenant_id` NO se pasa por parámetro: se deriva del contexto de tenant de la sesión (la misma
# fuente que usa la RLS), para que auditar y aislar no puedan discrepar. `payload_hash` vincula el
# snapshot de la acción (cuando el llamante lo aporta) sin guardar el payload crudo en el log.
_INSERT_AUDIT = text(
    "INSERT INTO audit_log (tenant_id, actor_id, action, entity, entity_id, payload_hash, "
    "request_id, source_ip) "
    "VALUES (NULLIF(current_setting('app.tenant_id', true), '')::uuid, "
    ":actor_id, :action, :entity, :entity_id, :payload_hash, :request_id, :source_ip)"
)


def _canonical_payload_hash(payload: dict[str, Any]) -> str:
    """SHA-256 hex del JSON canónico del payload (claves ordenadas, sin espacios superfluos).

    Canónico = determinista: el mismo snapshot produce siempre el mismo hash, de modo que la entrada
    del `audit_log` queda ligada de forma verificable al snapshot persistido (spec S2.5 §4/C8).
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def write_audit(
    session: AsyncSession,
    *,
    actor_id: UUID | None,
    action: str,
    entity: str,
    entity_id: UUID,
    payload: dict[str, Any] | None = None,
    request_id: str | None = None,
    source_ip: str | None = None,
) -> None:
    """Inserta una entrada en `audit_log` en el contexto de tenant de la sesión (append-only).

    `actor_id` es quien ejecuta la acción; `action` la acción de dominio (p. ej. `company.create`);
    `entity`/`entity_id` identifican la fila afectada. `payload` (opcional) es el snapshot de la
    acción: si viene, se guarda su `payload_hash` (SHA-256 del JSON canónico), vinculando la entrada
    al dato sin duplicarlo. No hace commit: participa en la transacción de la petición, de modo que
    la auditoría y el cambio de dominio son atómicos (o ambos, o nada).
    """
    await session.execute(
        _INSERT_AUDIT,
        {
            "actor_id": str(actor_id) if actor_id is not None else None,
            "action": action,
            "entity": entity,
            "entity_id": str(entity_id),
            "payload_hash": _canonical_payload_hash(payload) if payload is not None else None,
            "request_id": request_id,
            "source_ip": source_ip,
        },
    )
