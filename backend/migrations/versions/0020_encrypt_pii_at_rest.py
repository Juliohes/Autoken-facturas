"""Cifrado en reposo por tenant del CIF/nombre de empresas y contrapartes (S5.2).

Habilita `pgcrypto` y cifra con `pgp_sym_encrypt`/`pgp_sym_decrypt`, clave derivada por tenant
(nunca guardada en Postgres, ver `shared.encryption`): `companies.cif/name`,
`counterparties.cif/name`, `invoices.counterparty_tax_id/counterparty_name`,
`ocr_extractions.counterparty_tax_id/counterparty_name`. Añade un índice ciego (HMAC determinista,
`shared.encryption.blind_index`) donde hace falta comparar por igualdad sin descifrar:
- `companies.cif_blind_index` — sustituye al UNIQUE(tenant_id, cif) en claro (spec C3).
- `counterparties.cif_blind_index` — sustituye al UNIQUE(tenant_id, cif) Y a la búsqueda L2 por
  igualdad (`WHERE cif = ...`, ADR-0011) (spec C4).
- `invoices.counterparty_tax_id_blind_index` — sustituye al filtro `ILIKE` del panel (retirado,
  decisión de Julio) por un filtro EXACTO (spec C5).

`ocr_extractions` no lleva índice ciego: es la lectura cruda del OCR antes de confirmar, sin ningún
UNIQUE ni búsqueda por igualdad sobre esas columnas hoy.

`cif_lookups` queda FUERA de alcance a propósito (spec §4): es una caché global sin `tenant_id`
(ADR-0011), no encaja en el modelo de "clave por tenant".

El backfill de las filas ya existentes (columnas de texto plano) se hace aquí mismo, en Python,
usando `shared.config.get_settings().db_encryption_master_key` — la MISMA clave maestra que usará la
aplicación después. Las columnas de texto plano originales se eliminan al final: no quedan en
paralelo "por si acaso" (spec C8).

Revision ID: 0020_encrypt_pii_at_rest
Revises: 0019_ocr_ranking_entries
Create Date: 2026-07-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020_encrypt_pii_at_rest"
down_revision = "0019_ocr_ranking_entries"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"

# Tabla -> columnas de texto plano que se cifran, y si llevan índice ciego (para esas mismas
# columnas: el índice se llama "<columna>_blind_index"). Una sola fuente de verdad para el
# `upgrade`/`downgrade` (evita que las dos mitades diverjan).
_ENCRYPTED_COLUMNS: dict[str, dict[str, bool]] = {
    "companies": {"cif": True, "name": False},
    "counterparties": {"cif": True, "name": False},
    "invoices": {"counterparty_tax_id": True, "counterparty_name": False},
    "ocr_extractions": {"counterparty_tax_id": False, "counterparty_name": False},
}


def _backfill_table(connection: sa.engine.Connection, table: str, columns: dict[str, bool]) -> None:
    """Cifra en Python las filas ya existentes de `table`, fila a fila, con la clave del tenant al
    que pertenece cada una (derivada de `tenant_id` + la clave maestra real de la app)."""
    from shared.config import get_settings
    from shared.encryption import blind_index, derive_tenant_encryption_key
    from shared.tax_id import normalize_tax_id

    master_key = get_settings().db_encryption_master_key
    col_list = ", ".join(columns)
    rows = connection.execute(
        sa.text(f"SELECT id, tenant_id, {col_list} FROM {table}")  # noqa: S608 (tabla/columnas fijas, no input de usuario)
    ).mappings().all()

    for row in rows:
        tenant_key = derive_tenant_encryption_key(master_key, str(row["tenant_id"]))
        set_clauses = []
        params: dict[str, object] = {"id": row["id"], "key": tenant_key}
        for column, has_index in columns.items():
            value = row[column]
            set_clauses.append(f"{column}_new = pgp_sym_encrypt(:{column}, :key)")
            params[column] = value
            if has_index:
                # El índice ciego se calcula SIEMPRE sobre el valor normalizado (igual que la
                # aplicación en caliente, `shared.tax_id.normalize_tax_id`): `companies`/
                # `counterparties` ya guardan el CIF canónico, pero `invoices.counterparty_tax_id`
                # puede llevar el valor tal cual lo tecleó un humano (sin normalizar) — sin este
                # paso, el índice del backfill no coincidiría con el que calcula
                # `reporting.service` al filtrar, y el filtro exacto de CIF (C5) no encontraría esas
                # facturas tras migrar, en silencio.
                idx_value = (
                    blind_index(master_key, str(row["tenant_id"]), normalize_tax_id(value))
                    if value
                    else None
                )
                set_clauses.append(f"{column}_blind_index = :{column}_idx")
                params[f"{column}_idx"] = idx_value
        connection.execute(
            sa.text(f"UPDATE {table} SET {', '.join(set_clauses)} WHERE id = :id"),  # noqa: S608
            params,
        )


def _decrypt_backfill_table(
    connection: sa.engine.Connection, table: str, columns: dict[str, bool]
) -> None:
    """Inverso de `_backfill_table` (downgrade): descifra de vuelta a texto plano."""
    from shared.config import get_settings
    from shared.encryption import derive_tenant_encryption_key

    master_key = get_settings().db_encryption_master_key
    col_list = ", ".join(columns)
    rows = connection.execute(
        sa.text(f"SELECT id, tenant_id, {col_list} FROM {table}")  # noqa: S608
    ).mappings().all()

    for row in rows:
        tenant_key = derive_tenant_encryption_key(master_key, str(row["tenant_id"]))
        set_clauses = [f"{column}_plain = pgp_sym_decrypt({column}, :key)" for column in columns]
        connection.execute(
            sa.text(f"UPDATE {table} SET {', '.join(set_clauses)} WHERE id = :id"),  # noqa: S608
            {"id": row["id"], "key": tenant_key},
        )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    connection = op.get_bind()

    for table, columns in _ENCRYPTED_COLUMNS.items():
        for column, has_index in columns.items():
            op.add_column(table, sa.Column(f"{column}_new", postgresql.BYTEA()))
            if has_index:
                op.add_column(table, sa.Column(f"{column}_blind_index", sa.Text()))

        _backfill_table(connection, table, columns)

        for column, has_index in columns.items():
            op.alter_column(table, f"{column}_new", nullable=(_is_nullable(table, column)))

    # Companies: el UNIQUE(tenant_id, cif) en claro pasa a ser sobre el índice ciego (spec C3).
    op.drop_constraint("companies_tenant_cif_unique", "companies", type_="unique")
    op.drop_column("companies", "cif")
    op.drop_column("companies", "name")
    op.alter_column("companies", "cif_new", new_column_name="cif")
    op.alter_column("companies", "name_new", new_column_name="name")
    op.alter_column("companies", "cif", nullable=False)
    op.alter_column("companies", "name", nullable=False)
    op.alter_column("companies", "cif_blind_index", nullable=False)
    op.create_unique_constraint(
        "companies_tenant_cif_blind_index_unique", "companies", ["tenant_id", "cif_blind_index"]
    )

    # Counterparties: mismo patrón (UNIQUE + búsqueda L2 por igualdad, ADR-0011, spec C4).
    op.drop_constraint("counterparties_tenant_cif_unique", "counterparties", type_="unique")
    op.drop_column("counterparties", "cif")
    op.drop_column("counterparties", "name")
    op.alter_column("counterparties", "cif_new", new_column_name="cif")
    op.alter_column("counterparties", "name_new", new_column_name="name")
    op.alter_column("counterparties", "cif", nullable=False)
    op.alter_column("counterparties", "name", nullable=False)
    op.alter_column("counterparties", "cif_blind_index", nullable=False)
    op.create_unique_constraint(
        "counterparties_tenant_cif_blind_index_unique",
        "counterparties",
        ["tenant_id", "cif_blind_index"],
    )

    # Invoices: sin UNIQUE, pero el índice ciego sustituye al ILIKE retirado del panel (spec C5).
    op.drop_column("invoices", "counterparty_tax_id")
    op.drop_column("invoices", "counterparty_name")
    op.alter_column("invoices", "counterparty_tax_id_new", new_column_name="counterparty_tax_id")
    op.alter_column("invoices", "counterparty_name_new", new_column_name="counterparty_name")
    # Nulos permitidos: un CIF/nombre no legible sigue siendo NULL (anti-alucinación, spec §5).

    # ocr_extractions: cifrado, sin índice ciego (lectura cruda previa a confirmar, sin comparación).
    op.drop_column("ocr_extractions", "counterparty_tax_id")
    op.drop_column("ocr_extractions", "counterparty_name")
    op.alter_column(
        "ocr_extractions", "counterparty_tax_id_new", new_column_name="counterparty_tax_id"
    )
    op.alter_column("ocr_extractions", "counterparty_name_new", new_column_name="counterparty_name")

    # Solo la app (autoken_app) puede pedir a Postgres que cifre/descifre; nadie más ejecuta pgcrypto
    # a través de este rol salvo por sus propias consultas ya acotadas por RLS.
    op.execute(f"GRANT EXECUTE ON FUNCTION pgp_sym_encrypt(text, text) TO {_APP_ROLE}")
    op.execute(f"GRANT EXECUTE ON FUNCTION pgp_sym_decrypt(bytea, text) TO {_APP_ROLE}")


def _is_nullable(table: str, column: str) -> bool:
    """Companies/counterparties.cif/name eran NOT NULL; invoices/ocr_extractions.counterparty_* son
    nullable hoy (anti-alucinación: contraparte no legible = NULL). El cifrado conserva esa
    nulabilidad; se fija explícitamente tras el backfill, no antes (una fila con el valor viejo NULL
    no debe forzarse a cifrar algo)."""
    return table in ("invoices", "ocr_extractions")


def downgrade() -> None:
    connection = op.get_bind()

    for table, columns in _ENCRYPTED_COLUMNS.items():
        for column in columns:
            op.add_column(table, sa.Column(f"{column}_plain", sa.Text()))

    op.drop_constraint(
        "companies_tenant_cif_blind_index_unique", "companies", type_="unique"
    )
    op.drop_constraint(
        "counterparties_tenant_cif_blind_index_unique", "counterparties", type_="unique"
    )

    for table, columns in _ENCRYPTED_COLUMNS.items():
        _decrypt_backfill_table(connection, table, columns)
        for column, has_index in columns.items():
            op.drop_column(table, column)
            if has_index:
                op.drop_column(table, f"{column}_blind_index")
            op.alter_column(table, f"{column}_plain", new_column_name=column)

    op.alter_column("companies", "cif", nullable=False)
    op.alter_column("companies", "name", nullable=False)
    op.create_unique_constraint("companies_tenant_cif_unique", "companies", ["tenant_id", "cif"])
    op.alter_column("counterparties", "cif", nullable=False)
    op.alter_column("counterparties", "name", nullable=False)
    op.create_unique_constraint(
        "counterparties_tenant_cif_unique", "counterparties", ["tenant_id", "cif"]
    )

    op.execute(f"REVOKE EXECUTE ON FUNCTION pgp_sym_encrypt(text, text) FROM {_APP_ROLE}")
    op.execute(f"REVOKE EXECUTE ON FUNCTION pgp_sym_decrypt(bytea, text) FROM {_APP_ROLE}")
    # `pgcrypto` NO se deshabilita: es una extensión compartida, quitarla podría afectar a algo más
    # que esta tarea; revertir el downgrade a "no instalada" no es necesario para que los datos
    # vuelvan a texto plano (spec C8/C9 no lo exige).
