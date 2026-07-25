"""Tests de comportamiento S4.8: descubrimiento de candidatos del backfill del ranking
(spec docs/specs/S4.8-panel-ranking-multimodelo.md).

Criterio C12 (modo simulación). Postgres real; NUNCA invoca a ningún motor (el modo simulación no
lo necesita). La ejecución real queda fuera de esta tarea (spec §5/§6).
"""

from __future__ import annotations

from jobs.ocr_ranking_backfill import run_ranking_backfill
from ocr.ranking_backfill_repository import list_ranking_backfill_candidates
from shared.db import platform_session
from tests._dbtest import seed_company, seed_tenant, seed_user
from tests._ocr import (
    OWN_CIF,
    build_extracted,
    count_ranking_entries,
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


async def test_c12_lista_los_ficheros_sin_ninguna_entrada_de_ranking(authapi: Api) -> None:
    """C12: procesados con éxito sin ninguna entrada -> candidatos; ya rankeados, no."""
    _client, dsns = authapi

    _tenant_pending, _c1, _f1 = await _seed_file(dsns, slug="rkbf-pending", status="pending_ocr")
    tenant_elegible, c_elegible, f_elegible = await _seed_file(
        dsns, slug="rkbf-elegible", status="needs_review"
    )
    tenant_ya, c_ya, f_ya = await _seed_file(
        dsns, slug="rkbf-ya-rankeado", status="ocr_done", content=real_jpeg_bytes()
    )

    # `rkbf-ya-rankeado` ya tiene una entrada de ranking vigente: no debe reaparecer como candidato.
    # Se genera con un motor de ranking DOBLE inyectado explícitamente (nunca `ranking_extractors`
    # en blanco ni omitido: con el interruptor encendido y sin lista explícita, `run_ocr_ranking`
    # construiría los motores reales desde la config — este entorno de desarrollo SÍ tiene
    # credenciales reales configuradas, así que omitirlo dispararía llamadas de pago reales).
    await set_ocr_experiment_enabled(dsns, True)
    await run_ocr(
        tenant_id=tenant_ya,
        company_id=c_ya,
        file_id=f_ya,
        extractor=make_extractor(build_extracted()),
        ranking_extractors=[make_extractor(build_extracted(engine="gemini-3-flash"))],
    )
    await set_ocr_experiment_enabled(dsns, False)
    assert await count_ranking_entries(dsns, file_id=f_ya) >= 1

    async with platform_session() as session:
        candidates = await list_ranking_backfill_candidates(session)

    candidate_file_ids = {str(c.uploaded_file_id) for c in candidates}
    assert f_elegible in candidate_file_ids
    assert f_ya not in candidate_file_ids

    elegible = next(c for c in candidates if str(c.uploaded_file_id) == f_elegible)
    assert str(elegible.tenant_id) == tenant_elegible
    assert str(elegible.company_id) == c_elegible


async def test_c12_modo_simulacion_no_llama_a_ningun_motor_ni_escribe(authapi: Api) -> None:
    """C12: el propio modo simulación no invoca ningún extractor ni escribe filas."""
    _client, dsns = authapi
    _tenant, _company, file_id = await _seed_file(dsns, slug="rkbf-dry", status="needs_review")

    summary = await run_ranking_backfill(execute=False)

    assert summary.candidates >= 1
    assert summary.processed == 0
    assert await count_ranking_entries(dsns, file_id=file_id) == 0
