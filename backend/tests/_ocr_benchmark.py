"""Utilidades de test para S6.7 (benchmark real de variante x motor, spec
docs/specs/S6.7-benchmark-real-motor-variante.md).

No es un módulo de tests (prefijo `_`): consultas de efecto (superusuario) sobre
`ocr_benchmark_results`, para verificar lo que persiste `ocr.benchmark.run_benchmark` sin depender
de ningún endpoint todavía (los endpoints del panel son una tarea posterior, S6.7 parte 3).
"""

from __future__ import annotations

import json

import asyncpg


def _encryption_key_for(tenant_id: str) -> str:
    from shared.config import get_settings
    from shared.encryption import derive_tenant_encryption_key

    return derive_tenant_encryption_key(get_settings().db_encryption_master_key, tenant_id)


def _jsonb(value: object) -> object:
    """Normaliza una columna `jsonb` leída por `asyncpg` crudo (sin `set_type_codec`, a diferencia
    de la sesión SQLAlchemy que usa la app): sin codec, `asyncpg` devuelve el texto JSON tal cual,
    nunca lo decodifica solo (comprobado empíricamente contra Postgres real -- mismo criterio ya
    tolerado en `tests/test_ocr_worker.py::_confidences`). `None` se deja pasar (columna `NULL`,
    combinación caída, spec C2)."""
    return json.loads(value) if isinstance(value, str) else value


async def fetch_benchmark_results(dsns: dict[str, str], *, file_id: str) -> list[dict]:
    """Filas de `ocr_benchmark_results` de un fichero, con `counterparty_tax_id`/`counterparty_name`
    descifrados (S6.7 C23) — mismo patrón de dos consultas que
    `tests/_invoicing.py::_fetch_invoice_by` (la clave depende del `tenant_id`, hay que leerlo
    antes)."""
    conn = await asyncpg.connect(dsns["admin"])
    try:
        head = await conn.fetchrow(
            "SELECT tenant_id FROM ocr_benchmark_results WHERE uploaded_file_id = $1 LIMIT 1",
            file_id,
        )
        if head is None:
            return []
        key = _encryption_key_for(str(head["tenant_id"]))
        rows = await conn.fetch(
            "SELECT *, "
            "pgp_sym_decrypt(counterparty_tax_id, $2)::text AS __ctid, "
            "pgp_sym_decrypt(counterparty_name, $2)::text AS __cname "
            "FROM ocr_benchmark_results WHERE uploaded_file_id = $1 ORDER BY variant, engine",
            file_id,
            key,
        )
        results = []
        for row in rows:
            item = dict(row)
            item["counterparty_tax_id"] = item.pop("__ctid")
            item["counterparty_name"] = item.pop("__cname")
            item["reading"] = _jsonb(item["reading"])
            item["field_results"] = _jsonb(item["field_results"])
            results.append(item)
        return results
    finally:
        await conn.close()


async def fetch_benchmark_results_raw(dsns: dict[str, str], *, file_id: str) -> list[dict]:
    """Igual que `fetch_benchmark_results`, pero SIN descifrar -- para probar que el CIF/nombre de
    contraparte no viajan en claro (C23)."""
    conn = await asyncpg.connect(dsns["admin"])
    try:
        rows = await conn.fetch(
            "SELECT * FROM ocr_benchmark_results WHERE uploaded_file_id = $1 "
            "ORDER BY variant, engine",
            file_id,
        )
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def count_benchmark_results(dsns: dict[str, str], *, file_id: str) -> int:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        return int(
            await conn.fetchval(
                "SELECT count(*) FROM ocr_benchmark_results WHERE uploaded_file_id = $1", file_id
            )
        )
    finally:
        await conn.close()
