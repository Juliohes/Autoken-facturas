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


# Campos identificables de un cliente real (CIF/nombre de la contraparte). Desde S6.7 C24,
# `ocr_ranking_entries.reading` YA NO los lleva en claro (se cifran aparte en columnas `bytea`
# dedicadas antes de guardar, `ocr.ranking_repository.upsert_ranking_entry`) -- este filtro pasa a
# ser un no-op inofensivo en la práctica, no la única defensa. Se deja como defensa en profundidad
# (si algún día `reading` volviera a incluir esas claves por error, este endpoint seguiría sin
# exponerlas) y como documentación viva de qué es sensible en esta respuesta.
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
