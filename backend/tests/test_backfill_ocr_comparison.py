"""Tests de comportamiento S2.10: descubrimiento de candidatos del backfill
(spec docs/specs/S2.9-S2.10-preprocesado-comparativa.md).

Criterio C13 (modo simulación). Postgres real; NUNCA invoca al lector de IA (el modo simulación
no lo necesita). La ejecución real del backfill (invocar el lector sobre el histórico) queda
fuera de esta tarea (spec §5/§6): aquí solo se prueba que el descubrimiento sea correcto.
"""

from __future__ import annotations

from jobs.ocr_backfill import run_backfill
from ocr.backfill_repository import list_backfill_candidates
from shared.db import platform_session
from tests._dbtest import seed_company, seed_tenant, seed_user
from tests._intake import PDF, PDF_CT
from tests._ocr import (
    OWN_CIF,
    build_extracted,
    count_comparison_runs,
    make_extractor,
    real_jpeg_bytes,
    run_ocr,
    seed_uploaded_file,
    set_ocr_experiment_enabled,
)

Api = tuple[object, dict[str, str]]


async def _seed_file(dsns, *, slug: str, **file_kwargs) -> tuple[str, str, str]:
    tenant_id = await seed_tenant(dsns["admin"], slug, f"{slug.upper()} Asesoría")
    user_id = await seed_user(
        dsns["admin"], tenant_id=tenant_id, email=f"ana@{slug}.es", role="user"
    )
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Mi Empresa", cif=OWN_CIF
    )
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=user_id, **file_kwargs
    )
    return tenant_id, company_id, file_id


async def test_c13_lista_solo_los_ficheros_elegibles(authapi: Api) -> None:
    """C13: procesados con éxito, en formato imagen, sin comparativa todavía -> candidatos.

    Excluidos: sin procesar (`pending_ocr`), fallidos (`ocr_failed`), PDF (fuera de alcance de
    dominio, C3), y uno que YA tiene comparativa (no se repite sin querer).
    """
    _client, dsns = authapi

    _tenant_pending, _c1, _f1 = await _seed_file(dsns, slug="bf-pending", status="pending_ocr")
    _tenant_failed, _c2, _f2 = await _seed_file(dsns, slug="bf-failed", status="ocr_failed")
    tenant_pdf, c_pdf, f_pdf = await _seed_file(
        dsns, slug="bf-pdf", status="ocr_done", content=PDF, content_type=PDF_CT
    )
    tenant_elegible, c_elegible, f_elegible = await _seed_file(
        dsns, slug="bf-elegible", status="needs_review"
    )
    tenant_ya, c_ya, f_ya = await _seed_file(
        dsns, slug="bf-ya-comparado", status="ocr_done", content=real_jpeg_bytes()
    )

    # `bf-ya-comparado` ya tiene una comparativa vigente (interruptor ON al procesarla): no debe
    # reaparecer como candidato.
    await set_ocr_experiment_enabled(dsns, True)
    await run_ocr(
        tenant_id=tenant_ya,
        company_id=c_ya,
        file_id=f_ya,
        extractor=make_extractor(build_extracted()),
    )
    await set_ocr_experiment_enabled(dsns, False)

    async with platform_session() as session:
        candidates = await list_backfill_candidates(session)

    candidate_file_ids = {str(c.uploaded_file_id) for c in candidates}
    assert f_elegible in candidate_file_ids
    assert f_pdf not in candidate_file_ids
    assert f_ya not in candidate_file_ids

    elegible = next(c for c in candidates if str(c.uploaded_file_id) == f_elegible)
    assert str(elegible.tenant_id) == tenant_elegible
    assert str(elegible.company_id) == c_elegible


async def test_c13_modo_simulacion_no_llama_al_lector_ni_escribe(authapi: Api) -> None:
    """C13: el propio modo simulación no invoca ningún extractor ni escribe filas."""
    _client, dsns = authapi
    _tenant, _company, file_id = await _seed_file(dsns, slug="bf-dry", status="needs_review")

    summary = await run_backfill(execute=False)

    assert summary.candidates >= 1
    assert summary.processed == 0
    assert await count_comparison_runs(dsns, file_id=file_id) == 0
