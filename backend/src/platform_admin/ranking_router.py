"""Endpoints HTTP del ranking multi-modelo (S4.8): `GET /api/v1/platform/ocr-ranking` +
`GET /api/v1/platform/ocr-ranking/{engine}/examples` (2026-08-09, ejemplos concretos por motor,
a petición de Julio: "más contexto, ver ejemplos concretos, no solo números").

Capa HTTP fina: autentica y autoriza (`require_admin_tech`, exige `platform_admin` + el flag
`is_admin_tech`, comprobado fresco en cada petición) y delega en `ranking_service`. Un
`platform_admin` sin el flag recibe 403 (mismo criterio que el resto de `platform_admin`, C10).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from identity.authz import require_admin_tech
from identity.dependencies import AdminTechAuthContext
from platform_admin import ranking_service

router = APIRouter(prefix="/platform/ocr-ranking", tags=["platform"])

AdminTech = Annotated[AdminTechAuthContext, Depends(require_admin_tech())]


class EngineRankingOut(BaseModel):
    engine: str
    invoices_read: int
    average_score: float
    first_place_count: int


class EngineRankingExampleOut(BaseModel):
    uploaded_file_id: UUID
    model: str
    reading: dict[str, object]
    score: int


@router.get("")
async def get_ranking(identity: AdminTech) -> list[EngineRankingOut]:
    summary = await ranking_service.get_ranking_summary(identity.session)
    return [
        EngineRankingOut(
            engine=row.engine,
            invoices_read=row.invoices_read,
            average_score=row.average_score,
            first_place_count=row.first_place_count,
        )
        for row in summary
    ]


# Campos identificables de un cliente real (CIF/nombre de la contraparte) que este endpoint NUNCA
# expone, aunque `ocr_ranking_entries.reading` los guarde en claro (S5.2 §6, decisión pendiente de
# Julio antes de activar el experimento en producción — que ya está activo, con datos reales). El
# resto de este router ya agrega A TRAVÉS de todos los tenants (`get_ranking`, C11 auditado); este
# endpoint añade el mismo alcance cross-tenant pero a nivel de lectura individual, así que redacta
# aquí lo identificable en vez de reabrir esa decisión pendiente (auditoría, hallazgo crítico).
_REDACTED_READING_FIELDS = frozenset({"counterparty_tax_id", "counterparty_name"})


def _redact_reading(reading: dict[str, object]) -> dict[str, object]:
    return {k: v for k, v in reading.items() if k not in _REDACTED_READING_FIELDS}


@router.get("/{engine}/examples")
async def get_ranking_examples(identity: AdminTech, engine: str) -> list[EngineRankingExampleOut]:
    """Hasta 5 lecturas reales de este motor, la más reciente primero. Motor sin ninguna lectura
    todavía -> lista vacía (nunca un error)."""
    examples = await ranking_service.get_ranking_examples(identity.session, engine)
    return [
        EngineRankingExampleOut(
            uploaded_file_id=row.uploaded_file_id,
            model=row.model,
            reading=_redact_reading(row.reading),
            score=row.score,
        )
        for row in examples
    ]
