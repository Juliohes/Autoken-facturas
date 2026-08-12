"""Tests de comportamiento S6.7 C24 (spec docs/specs/S6.7-benchmark-real-motor-variante.md): el CIF
y el nombre de contraparte de los experimentos ya existentes (`ocr_comparison_runs` S2.10,
`ocr_ranking_entries` S4.8) dejan de viajar en claro dentro de `reading`/`original_reading`/
`enhanced_reading` (JSONB) -- mismo hallazgo ya corregido en `ocr_benchmark_results` (S6.7 parte 2,
C23): esos dos campos pasan a columnas `bytea` dedicadas, cifradas con la clave del tenant
(ADR-0018), fuera de cualquier JSONB.

Postgres real. Cubre el camino de ESCRITURA NUEVA (`upsert_comparison_run`/`upsert_ranking_entry`,
llamado con un `encryption_key` ya derivado, mismo patrón que `ocr.benchmark_repository`). El
backfill de las filas YA EXISTENTES en producción (la migración en sí) se verifica aparte, de forma
manual contra Postgres real (mismo criterio que la migración 0020, S5.2 -- no hay un test de pytest
dedicado para el propio backfill de una migración en este proyecto).
"""

from __future__ import annotations

import asyncpg


def _encryption_key_for(tenant_id: str) -> str:
    from shared.config import get_settings
    from shared.encryption import derive_tenant_encryption_key

    return derive_tenant_encryption_key(get_settings().db_encryption_master_key, tenant_id)


async def _fetch_comparison_run_raw(dsns: dict[str, str], *, file_id: str) -> dict:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow(
            "SELECT * FROM ocr_comparison_runs WHERE uploaded_file_id = $1", file_id
        )
        assert row is not None
        return dict(row)
    finally:
        await conn.close()


async def _fetch_ranking_entry_raw(dsns: dict[str, str], *, file_id: str, engine: str) -> dict:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow(
            "SELECT * FROM ocr_ranking_entries WHERE uploaded_file_id = $1 AND engine = $2",
            file_id,
            engine,
        )
        assert row is not None
        return dict(row)
    finally:
        await conn.close()


async def test_c24_comparison_runs_no_guarda_el_cif_ni_el_nombre_en_claro(authapi) -> None:
    """spec: C24 -- `original_reading`/`enhanced_reading` no deben contener el CIF/nombre de
    contraparte en ningún punto de su texto JSON; viajan cifrados en columnas dedicadas."""
    from ocr.comparison_repository import upsert_comparison_run
    from shared.db import tenant_session
    from tests._dbtest import seed_company, seed_tenant
    from tests._invoicing import COUNTERPARTY_CIF
    from tests._ocr import OWN_CIF, seed_uploaded_file

    _client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "cmp-c24", "CMP C24 Asesoría")
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Mi Empresa", cif=OWN_CIF
    )
    from tests._dbtest import seed_user

    user_id = await seed_user(dsns["admin"], tenant_id=tenant_id, email="a@cmp-c24.es", role="user")
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=user_id
    )

    reading = {
        "counterparty_tax_id": COUNTERPARTY_CIF,
        "counterparty_name": "Proveedor SA",
        "total_amount": "121.00",
    }
    key = _encryption_key_for(tenant_id)
    async with tenant_session(tenant_id, company_id) as session:
        await upsert_comparison_run(
            session,
            company_id=company_id,
            uploaded_file_id=file_id,
            original_reading=dict(reading),
            enhanced_reading=dict(reading),
            original_score=5,
            enhanced_score=5,
            winner="tie",
            engine="fake",
            model="fake-1",
            encryption_key=key,
        )

    raw = await _fetch_comparison_run_raw(dsns, file_id=file_id)
    assert COUNTERPARTY_CIF not in str(raw["original_reading"])
    assert "Proveedor SA" not in str(raw["original_reading"])
    assert COUNTERPARTY_CIF not in str(raw["enhanced_reading"])
    assert "Proveedor SA" not in str(raw["enhanced_reading"])
    assert raw["original_counterparty_tax_id"] is not None

    conn = await asyncpg.connect(dsns["admin"])
    try:
        decrypted = await conn.fetchrow(
            "SELECT pgp_sym_decrypt(original_counterparty_tax_id, $2)::text AS cif, "
            "pgp_sym_decrypt(original_counterparty_name, $2)::text AS name "
            "FROM ocr_comparison_runs WHERE uploaded_file_id = $1",
            file_id,
            key,
        )
    finally:
        await conn.close()
    assert decrypted["cif"] == COUNTERPARTY_CIF
    assert decrypted["name"] == "Proveedor SA"


async def test_c24_ranking_entries_no_guarda_el_cif_ni_el_nombre_en_claro(authapi) -> None:
    """spec: C24 -- igual que arriba, para `ocr_ranking_entries` (una fila por motor)."""
    from ocr.ranking_repository import upsert_ranking_entry
    from shared.db import tenant_session
    from tests._dbtest import seed_company, seed_tenant, seed_user
    from tests._invoicing import COUNTERPARTY_CIF
    from tests._ocr import OWN_CIF, seed_uploaded_file

    _client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "rk-c24", "RK C24 Asesoría")
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Mi Empresa", cif=OWN_CIF
    )
    user_id = await seed_user(dsns["admin"], tenant_id=tenant_id, email="a@rk-c24.es", role="user")
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=user_id
    )

    key = _encryption_key_for(tenant_id)
    async with tenant_session(tenant_id, company_id) as session:
        await upsert_ranking_entry(
            session,
            company_id=company_id,
            uploaded_file_id=file_id,
            engine="gemini-3-flash",
            model="gemini-3-flash-001",
            reading={
                "counterparty_tax_id": COUNTERPARTY_CIF,
                "counterparty_name": "Proveedor SA",
                "total_amount": "121.00",
            },
            score=5,
            encryption_key=key,
        )

    raw = await _fetch_ranking_entry_raw(dsns, file_id=file_id, engine="gemini-3-flash")
    assert COUNTERPARTY_CIF not in str(raw["reading"])
    assert "Proveedor SA" not in str(raw["reading"])
    assert raw["counterparty_tax_id"] is not None

    conn = await asyncpg.connect(dsns["admin"])
    try:
        decrypted = await conn.fetchrow(
            "SELECT pgp_sym_decrypt(counterparty_tax_id, $2)::text AS cif, "
            "pgp_sym_decrypt(counterparty_name, $2)::text AS name "
            "FROM ocr_ranking_entries WHERE uploaded_file_id = $1 AND engine = $3",
            file_id,
            key,
            "gemini-3-flash",
        )
    finally:
        await conn.close()
    assert decrypted["cif"] == COUNTERPARTY_CIF
    assert decrypted["name"] == "Proveedor SA"
