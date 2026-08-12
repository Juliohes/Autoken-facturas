"""Cifra el CIF/nombre de contraparte de los experimentos ya existentes (S6.7 C24, spec
docs/specs/S6.7-benchmark-real-motor-variante.md, Área F).

`ocr_comparison_runs` (S2.10) y `ocr_ranking_entries` (S4.8) guardaban `counterparty_tax_id`/
`counterparty_name` EN CLARO dentro de sus columnas JSONB (`original_reading`/`enhanced_reading`/
`reading`) -- hallazgo ya documentado y aplazado desde la auditoría de S4.8 (2026-08-09), que Julio
confirmó explícitamente resolver ahora, ya que S6.7 sustituye el módulo de escritura de ambas
tablas. Mismo criterio ya aplicado (y auditado) en `ocr_benchmark_results` (S6.7 parte 2, C23) y en
`companies`/`counterparties`/`invoices`/`ocr_extractions` (S5.2, migración 0020): esos dos campos
pasan a columnas `bytea` dedicadas, cifradas con la clave del tenant (ADR-0018), FUERA de cualquier
JSONB -- nunca en claro, ni siquiera duplicados junto a la versión cifrada.

El backfill de las filas ya existentes se hace aquí mismo, en Python, exactamente igual que
`0020_encrypt_pii_at_rest::_backfill_table`: para cada fila, deriva la clave de SU tenant
(`shared.encryption.derive_tenant_encryption_key`, a partir de
`shared.config.get_settings().db_encryption_master_key` -- la MISMA clave maestra que usa la app
después) y hace un `UPDATE` que (a) cifra el CIF/nombre extraídos del JSONB en las columnas nuevas y
(b) quita esas dos claves del propio JSONB en la MISMA sentencia (operador `-` de `jsonb`, quita una
clave), para que no queden duplicadas en claro. `pgp_sym_encrypt` es `STRICT` (NULL entra, NULL
sale): una fila sin esa clave en el JSONB (nunca se leyó/identificó una contraparte) cifra `NULL`
sin problema, igual que en toda migración anterior de cifrado de este proyecto.

`pgp_sym_encrypt`/`pgp_sym_decrypt` ya están concedidos a `autoken_app` desde la migración 0020 (son
funciones de la extensión `pgcrypto`, compartida): esta migración no repite ese GRANT.

Revision ID: 0033_encrypt_ocr_experiment_pii
Revises: 0032_benchmark_field_ranking
Create Date: 2026-08-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0033_encrypt_ocr_experiment_pii"
down_revision = "0032_benchmark_field_ranking"
branch_labels = None
depends_on = None


def _backfill_comparison_runs(connection: sa.engine.Connection) -> None:
    """Cifra el CIF/nombre de `ocr_comparison_runs` -- dos pares (original/enhanced), cada uno
    puede diferir entre la lectura original y la realzada."""
    from shared.config import get_settings
    from shared.encryption import derive_tenant_encryption_key

    master_key = get_settings().db_encryption_master_key
    rows = connection.execute(
        sa.text(
            "SELECT id, tenant_id, original_reading, enhanced_reading FROM ocr_comparison_runs"
        )
    ).mappings().all()

    for row in rows:
        tenant_key = derive_tenant_encryption_key(master_key, str(row["tenant_id"]))
        original = row["original_reading"] or {}
        enhanced = row["enhanced_reading"] or {}
        connection.execute(
            sa.text(
                "UPDATE ocr_comparison_runs SET "
                "original_counterparty_tax_id = pgp_sym_encrypt(:original_tax_id, :key), "
                "original_counterparty_name = pgp_sym_encrypt(:original_name, :key), "
                "enhanced_counterparty_tax_id = pgp_sym_encrypt(:enhanced_tax_id, :key), "
                "enhanced_counterparty_name = pgp_sym_encrypt(:enhanced_name, :key), "
                "original_reading = original_reading - 'counterparty_tax_id' - 'counterparty_name', "  # noqa: E501
                "enhanced_reading = enhanced_reading - 'counterparty_tax_id' - 'counterparty_name' "
                "WHERE id = :id"
            ),
            {
                "id": row["id"],
                "key": tenant_key,
                "original_tax_id": original.get("counterparty_tax_id"),
                "original_name": original.get("counterparty_name"),
                "enhanced_tax_id": enhanced.get("counterparty_tax_id"),
                "enhanced_name": enhanced.get("counterparty_name"),
            },
        )


def _decrypt_comparison_runs(connection: sa.engine.Connection) -> None:
    """Inverso de `_backfill_comparison_runs` (downgrade): descifra de vuelta a las claves del
    JSONB, usando `jsonb_set` para reinsertarlas."""
    from shared.config import get_settings
    from shared.encryption import derive_tenant_encryption_key

    master_key = get_settings().db_encryption_master_key
    # `pgp_sym_decrypt` necesita la clave REAL de cada fila (derivada de su `tenant_id`), así que se
    # lee primero el id/tenant de cada fila y se descifra fila a fila abajo (mismo patrón que
    # `0020_encrypt_pii_at_rest::_decrypt_backfill_table`).
    rows = connection.execute(
        sa.text(
            "SELECT id, tenant_id, original_counterparty_tax_id, original_counterparty_name, "
            "enhanced_counterparty_tax_id, enhanced_counterparty_name "
            "FROM ocr_comparison_runs"
        )
    ).mappings().all()

    for row in rows:
        tenant_key = derive_tenant_encryption_key(master_key, str(row["tenant_id"]))
        decrypted = connection.execute(
            sa.text(
                "SELECT pgp_sym_decrypt(original_counterparty_tax_id, :key)::text AS original_tax_id, "  # noqa: E501
                "pgp_sym_decrypt(original_counterparty_name, :key)::text AS original_name, "
                "pgp_sym_decrypt(enhanced_counterparty_tax_id, :key)::text AS enhanced_tax_id, "
                "pgp_sym_decrypt(enhanced_counterparty_name, :key)::text AS enhanced_name "
                "FROM ocr_comparison_runs WHERE id = :id"
            ),
            {"key": tenant_key, "id": row["id"]},
        ).mappings().one()
        connection.execute(
            sa.text(
                "UPDATE ocr_comparison_runs SET "
                "original_reading = jsonb_set(jsonb_set(original_reading, "
                "  '{counterparty_tax_id}', COALESCE(to_jsonb((:original_tax_id)::text), 'null'::jsonb), true), "  # noqa: E501
                "  '{counterparty_name}', COALESCE(to_jsonb((:original_name)::text), 'null'::jsonb), true), "  # noqa: E501
                "enhanced_reading = jsonb_set(jsonb_set(enhanced_reading, "
                "  '{counterparty_tax_id}', COALESCE(to_jsonb((:enhanced_tax_id)::text), 'null'::jsonb), true), "  # noqa: E501
                "  '{counterparty_name}', COALESCE(to_jsonb((:enhanced_name)::text), 'null'::jsonb), true) "  # noqa: E501
                "WHERE id = :id"
            ),
            {
                "id": row["id"],
                "original_tax_id": decrypted["original_tax_id"],
                "original_name": decrypted["original_name"],
                "enhanced_tax_id": decrypted["enhanced_tax_id"],
                "enhanced_name": decrypted["enhanced_name"],
            },
        )


def _backfill_ranking_entries(connection: sa.engine.Connection) -> None:
    """Cifra el CIF/nombre de `ocr_ranking_entries` -- una única columna `reading`."""
    from shared.config import get_settings
    from shared.encryption import derive_tenant_encryption_key

    master_key = get_settings().db_encryption_master_key
    rows = connection.execute(
        sa.text("SELECT id, tenant_id, reading FROM ocr_ranking_entries")
    ).mappings().all()

    for row in rows:
        tenant_key = derive_tenant_encryption_key(master_key, str(row["tenant_id"]))
        reading = row["reading"] or {}
        connection.execute(
            sa.text(
                "UPDATE ocr_ranking_entries SET "
                "counterparty_tax_id = pgp_sym_encrypt(:tax_id, :key), "
                "counterparty_name = pgp_sym_encrypt(:name, :key), "
                "reading = reading - 'counterparty_tax_id' - 'counterparty_name' "
                "WHERE id = :id"
            ),
            {
                "id": row["id"],
                "key": tenant_key,
                "tax_id": reading.get("counterparty_tax_id"),
                "name": reading.get("counterparty_name"),
            },
        )


def _decrypt_ranking_entries(connection: sa.engine.Connection) -> None:
    """Inverso de `_backfill_ranking_entries` (downgrade)."""
    from shared.config import get_settings
    from shared.encryption import derive_tenant_encryption_key

    master_key = get_settings().db_encryption_master_key
    rows = connection.execute(
        sa.text(
            "SELECT id, tenant_id, counterparty_tax_id, counterparty_name FROM ocr_ranking_entries"
        )
    ).mappings().all()

    for row in rows:
        tenant_key = derive_tenant_encryption_key(master_key, str(row["tenant_id"]))
        decrypted = connection.execute(
            sa.text(
                "SELECT pgp_sym_decrypt(counterparty_tax_id, :key)::text AS tax_id, "
                "pgp_sym_decrypt(counterparty_name, :key)::text AS name "
                "FROM ocr_ranking_entries WHERE id = :id"
            ),
            {"key": tenant_key, "id": row["id"]},
        ).mappings().one()
        connection.execute(
            sa.text(
                "UPDATE ocr_ranking_entries SET "
                "reading = jsonb_set(jsonb_set(reading, "
                "  '{counterparty_tax_id}', COALESCE(to_jsonb((:tax_id)::text), 'null'::jsonb), true), "  # noqa: E501
                "  '{counterparty_name}', COALESCE(to_jsonb((:name)::text), 'null'::jsonb), true) "
                "WHERE id = :id"
            ),
            {"id": row["id"], "tax_id": decrypted["tax_id"], "name": decrypted["name"]},
        )


def upgrade() -> None:
    # El runbook exige detener API/worker. Este lock cierra además la ventana contra cualquier
    # conexión antigua que aún estuviera terminando de escribir durante el backfill.
    op.execute("LOCK TABLE ocr_comparison_runs, ocr_ranking_entries IN SHARE ROW EXCLUSIVE MODE")
    op.add_column(
        "ocr_comparison_runs", sa.Column("original_counterparty_tax_id", postgresql.BYTEA())
    )
    op.add_column(
        "ocr_comparison_runs", sa.Column("original_counterparty_name", postgresql.BYTEA())
    )
    op.add_column(
        "ocr_comparison_runs", sa.Column("enhanced_counterparty_tax_id", postgresql.BYTEA())
    )
    op.add_column(
        "ocr_comparison_runs", sa.Column("enhanced_counterparty_name", postgresql.BYTEA())
    )
    op.add_column("ocr_ranking_entries", sa.Column("counterparty_tax_id", postgresql.BYTEA()))
    op.add_column("ocr_ranking_entries", sa.Column("counterparty_name", postgresql.BYTEA()))

    connection = op.get_bind()
    _backfill_comparison_runs(connection)
    _backfill_ranking_entries(connection)


def downgrade() -> None:
    connection = op.get_bind()
    _decrypt_comparison_runs(connection)
    _decrypt_ranking_entries(connection)

    op.drop_column("ocr_comparison_runs", "original_counterparty_tax_id")
    op.drop_column("ocr_comparison_runs", "original_counterparty_name")
    op.drop_column("ocr_comparison_runs", "enhanced_counterparty_tax_id")
    op.drop_column("ocr_comparison_runs", "enhanced_counterparty_name")
    op.drop_column("ocr_ranking_entries", "counterparty_tax_id")
    op.drop_column("ocr_ranking_entries", "counterparty_name")
