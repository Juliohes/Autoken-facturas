"""Acceso a datos de `ocr_benchmark_batch_runs` (S6.7 Área C, migración 0030).

A diferencia de la migración 0030 original, el rol runtime (`autoken_app`) ya NO tiene acceso
directo a esta tabla (migración 0031, S6.7 auditoría 2026-08-11, hallazgo de coherencia con
`platform_settings`/0017 -- el único precedente comparable de tabla de plataforma sin
`tenant_id`/RLS, que deliberadamente nunca concedió acceso directo). Todo el acceso pasa por
funciones `SECURITY DEFINER` de superficie fija (`get_running_batch_run`/`get_latest_batch_run`/
`insert_running_batch_run`, migración 0031) -- mismo patrón que el resto de `platform_admin`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["BatchRun", "get_by_id", "get_latest", "get_running", "list_candidates", "start"]


@dataclass(frozen=True)
class BatchRun:
    id: UUID
    status: str
    total: int
    completed: int
    failed_count: int


def _to_batch_run(row: Any) -> BatchRun:
    return BatchRun(
        id=row.id,
        status=row.status,
        total=row.total,
        completed=row.completed,
        failed_count=row.failed_count,
    )


async def get_running(session: AsyncSession) -> BatchRun | None:
    """El lote `running` más reciente, o `None` si no hay ninguno corriendo (C11/C16)."""
    row = (await session.execute(text("SELECT * FROM get_running_batch_run()"))).first()
    return _to_batch_run(row) if row is not None else None


async def get_latest(session: AsyncSession) -> BatchRun | None:
    """El lote más reciente (cualquier estado), o `None` si nunca se lanzó ninguno (C16)."""
    row = (await session.execute(text("SELECT * FROM get_latest_batch_run()"))).first()
    return _to_batch_run(row) if row is not None else None


async def get_by_id(session: AsyncSession, batch_run_id: str) -> BatchRun | None:
    """Lee un lote tras tomar el candado para ignorar redeliveries ya cerrados."""
    row = (
        await session.execute(text("SELECT * FROM get_batch_run(:id)"), {"id": batch_run_id})
    ).first()
    return _to_batch_run(row) if row is not None else None


async def start(session: AsyncSession, *, limit: int) -> tuple[bool, BatchRun]:
    """Crea el lote y su snapshot de candidatos atómicamente, o devuelve el lote en curso."""
    row = (
        await session.execute(
            text("SELECT * FROM start_benchmark_batch(:limit)"), {"limit": limit}
        )
    ).one()
    return row.started, _to_batch_run(row)


async def list_candidates(session: AsyncSession, batch_run_id: str) -> list[tuple[str, str, str]]:
    rows = (
        await session.execute(
            text("SELECT * FROM get_benchmark_batch_candidates(:id)"), {"id": batch_run_id}
        )
    ).all()
    return [(str(row.tenant_id), str(row.company_id), str(row.uploaded_file_id)) for row in rows]
