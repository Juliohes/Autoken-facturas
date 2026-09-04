"""Acceso a datos del benchmark real de variante x motor (S6.7, spec
docs/specs/S6.7-benchmark-real-motor-variante.md, Área A/C1-C4/C9/C23): SQL de
`ocr_benchmark_results`.

Mismo patrón que `ocr.ranking_repository` (S4.8): la sesión llega ya abierta en el contexto de
tenant (RLS de dos niveles); el `tenant_id` de la escritura sale de `app.tenant_id` (nunca por
parámetro); upsert por `(uploaded_file_id, variant, engine)` (idempotencia, C4).

`counterparty_tax_id`/`counterparty_name` viajan cifrados con la clave del tenant (C23, mismo patrón
ADR-0018 que `invoices`/`companies` desde S5.2) en dos columnas `bytea` dedicadas -- decisión de
alcance de esta tarea (ver docstring de `ocr.benchmark`): el resto de la lectura (fechas, importes,
tramos de IVA, número de factura) va en `reading` JSONB EN CLARO, sin esos dos campos dentro.
`encryption_key` llega ya derivada (mismo criterio ya establecido para el resto del proyecto desde
la auditoría de S5.2: el repositorio nunca deriva claves, solo las usa -- lo hace el llamador,
`ocr.benchmark`, con `shared.encryption.tenant_encryption_key`).

`pgp_sym_encrypt`/`pgp_sym_decrypt` son funciones STRICT (NULL entra, NULL sale, igual que
`invoicing.repository`): una combinación caída (C2, sin contraparte leída) cifra `NULL` sin
problema. `reading`/`field_results` distinguen "sin lectura" (`None` -> SQL `NULL`, combinación
caída) de "lectura con 0 campos" (`field_results=[]`, sigue siendo una lista JSON válida, nunca
`NULL`) -- por eso `reading` NO se serializa con `json.dumps` cuando es `None`: `json.dumps(None)`
produce el texto `"null"`, que `CAST(... AS jsonb)` convertiría en un JSON `null` (una fila CON
valor), no en un SQL `NULL` de verdad (la fila sin valor que exige la spec, "sin lectura").
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["BenchmarkEntry", "list_benchmark_entries", "upsert_benchmark_result"]


@dataclass(frozen=True)
class BenchmarkEntry:
    variant: str
    engine: str
    field_results: list[dict[str, Any]]
    tax_lines_matched: bool | None


_TENANT_FROM_CONTEXT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

_UPSERT = text(
    f"INSERT INTO ocr_benchmark_results "
    f"(tenant_id, company_id, uploaded_file_id, variant, engine, model, "
    f" counterparty_tax_id, counterparty_name, reading, field_results, tax_lines_matched, "
    f" aciertos, comparables, error, duration_ms, benchmark_contract_version, schema_version, "
    f" normalization_version, ground_truth_hash, document_sha256, variant_sha256, pages, "
    f" field_exact_accuracy, critical_field_accuracy, all_critical_exact, arithmetic_valid, "
    f" hallucination_flags, manual_corrections_per_invoice, api_cost_usd) "
    f"VALUES ({_TENANT_FROM_CONTEXT}, :company_id, :uploaded_file_id, :variant, :engine, :model, "
    f" pgp_sym_encrypt(:counterparty_tax_id, :key), pgp_sym_encrypt(:counterparty_name, :key), "
    f" CAST(:reading AS jsonb), CAST(:field_results AS jsonb), :tax_lines_matched, "
    f" :aciertos, :comparables, :error, :duration_ms, :benchmark_contract_version, "
    f" :schema_version, "
    f" :normalization_version, :ground_truth_hash, :document_sha256, :variant_sha256, :pages, "
    f" :field_exact_accuracy, :critical_field_accuracy, :all_critical_exact, :arithmetic_valid, "
    f" CAST(:hallucination_flags AS jsonb), :manual_corrections_per_invoice, :api_cost_usd) "
    f"ON CONFLICT (uploaded_file_id, variant, engine) DO UPDATE SET "
    f" model = EXCLUDED.model, "
    f" counterparty_tax_id = EXCLUDED.counterparty_tax_id, "
    f" counterparty_name = EXCLUDED.counterparty_name, "
    f" reading = EXCLUDED.reading, "
    f" field_results = EXCLUDED.field_results, "
    f" tax_lines_matched = EXCLUDED.tax_lines_matched, "
    f" aciertos = EXCLUDED.aciertos, "
    f" comparables = EXCLUDED.comparables, "
    f" error = EXCLUDED.error, "
    f" duration_ms = EXCLUDED.duration_ms, "
    f" benchmark_contract_version = EXCLUDED.benchmark_contract_version, "
    f" schema_version = EXCLUDED.schema_version, "
    f" normalization_version = EXCLUDED.normalization_version, "
    f" ground_truth_hash = EXCLUDED.ground_truth_hash, "
    f" document_sha256 = EXCLUDED.document_sha256, "
    f" variant_sha256 = EXCLUDED.variant_sha256, "
    f" pages = EXCLUDED.pages, "
    f" field_exact_accuracy = EXCLUDED.field_exact_accuracy, "
    f" critical_field_accuracy = EXCLUDED.critical_field_accuracy, "
    f" all_critical_exact = EXCLUDED.all_critical_exact, "
    f" arithmetic_valid = EXCLUDED.arithmetic_valid, "
    f" hallucination_flags = EXCLUDED.hallucination_flags, "
    f" manual_corrections_per_invoice = EXCLUDED.manual_corrections_per_invoice, "
    f" api_cost_usd = EXCLUDED.api_cost_usd, "
    f" updated_at = now()"
)


async def upsert_benchmark_result(
    session: AsyncSession,
    *,
    company_id: UUID,
    uploaded_file_id: UUID,
    variant: str,
    engine: str,
    model: str | None,
    counterparty_tax_id: str | None,
    counterparty_name: str | None,
    reading: dict[str, Any] | None,
    field_results: list[dict[str, Any]],
    tax_lines_matched: bool | None,
    aciertos: int,
    comparables: int,
    error: str | None,
    duration_ms: int | None,
    benchmark_contract_version: str,
    schema_version: str,
    normalization_version: str,
    ground_truth_hash: str,
    document_sha256: str,
    variant_sha256: str | None,
    pages: int,
    field_exact_accuracy: float | None,
    critical_field_accuracy: float | None,
    all_critical_exact: bool | None,
    arithmetic_valid: bool | None,
    hallucination_flags: list[str],
    manual_corrections_per_invoice: int | None,
    api_cost_usd: str | None,
    encryption_key: str,
) -> None:
    """Inserta o reemplaza el resultado de esta combinación (variante, motor) para este fichero
    (idempotente, C4). `model`/`counterparty_tax_id`/`counterparty_name`/`reading`/
    `tax_lines_matched`/`duration_ms` a `None` en una combinación caída (C2); `error` a `None` en
    una combinación con éxito -- nunca las dos cosas a la vez."""
    await session.execute(
        _UPSERT,
        {
            "company_id": str(company_id),
            "uploaded_file_id": str(uploaded_file_id),
            "variant": variant,
            "engine": engine,
            "model": model,
            "counterparty_tax_id": counterparty_tax_id,
            "counterparty_name": counterparty_name,
            "reading": json.dumps(reading) if reading is not None else None,
            "field_results": json.dumps(field_results),
            "tax_lines_matched": tax_lines_matched,
            "aciertos": aciertos,
            "comparables": comparables,
            "error": error,
            "duration_ms": duration_ms,
            "benchmark_contract_version": benchmark_contract_version,
            "schema_version": schema_version,
            "normalization_version": normalization_version,
            "ground_truth_hash": ground_truth_hash,
            "document_sha256": document_sha256,
            "variant_sha256": variant_sha256,
            "pages": pages,
            "field_exact_accuracy": field_exact_accuracy,
            "critical_field_accuracy": critical_field_accuracy,
            "all_critical_exact": all_critical_exact,
            "arithmetic_valid": arithmetic_valid,
            "hallucination_flags": json.dumps(hallucination_flags),
            "manual_corrections_per_invoice": manual_corrections_per_invoice,
            "api_cost_usd": api_cost_usd,
            "key": encryption_key,
        },
    )


async def list_benchmark_entries(
    session: AsyncSession, uploaded_file_id: UUID
) -> list[BenchmarkEntry]:
    """Resultados reales variante x motor de una factura para el Laboratorio (S6.7 C21/C22).

    No lee la lectura cruda ni los campos cifrados: el diagnóstico necesita solo el acierto por
    campo ya calculado contra la verdad confirmada.
    """
    rows = (
        await session.execute(
            text(
                "SELECT variant, engine, field_results, tax_lines_matched "
                "FROM ocr_benchmark_results WHERE uploaded_file_id = :fid "
                "ORDER BY variant, engine"
            ),
            {"fid": str(uploaded_file_id)},
        )
    ).all()
    return [
        BenchmarkEntry(
            variant=row.variant,
            engine=row.engine,
            field_results=list(row.field_results),
            tax_lines_matched=row.tax_lines_matched,
        )
        for row in rows
    ]
