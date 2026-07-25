"""Endpoint HTTP del ranking multi-modelo (S4.8): `GET /api/v1/platform/ocr-ranking`.

Capa HTTP fina: autentica y autoriza (`require_admin_tech`, exige `platform_admin` + el flag
`is_admin_tech`, comprobado fresco en cada petición) y delega en `ranking_service`. Un
`platform_admin` sin el flag recibe 403 (mismo criterio que el resto de `platform_admin`, C10).
"""

from __future__ import annotations

from typing import Annotated

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
