"""Ranking agregado del benchmark real por grupo de campo y por combinación (S6.7 Área D, spec
docs/specs/S6.7-benchmark-real-motor-variante.md, C18-C20).

Sustituye la vista principal del panel de ranking S4.8 (que NO se toca, sigue existiendo tal cual
-- spec §6) por un agregado más útil: en vez de un único ranking global por motor, dos vistas sobre
`ocr_benchmark_results` (S6.7 Área A, migración 0029):

- `ocr_benchmark_field_group_ranking()`: aciertos/comparables por (grupo de campo, variant, engine).
  Dos motores que ganan en grupos DISTINTOS (uno en CIF/NIF, otro en Fecha) deben verse los dos, no
  un ganador global que esconda la fortaleza de cada uno (C18). Seis de los siete grupos salen de
  `field_results` (JSONB, una entrada por campo escalar); "Tramos IVA" sale de la columna propia
  `tax_lines_matched` (no vive dentro de `field_results`, C18 -- verificado explícitamente por un
  test que lo separa de "Importes"). Las filas con `error IS NOT NULL` no aportan lectura real y se
  excluyen de la agregación (mismo criterio que la fila fallida no tiene `field_results` real,
  `ocr.benchmark._CombinationResult`).

- `ocr_benchmark_combination_summary()`: por (variant, engine), sobre TODAS las filas (con y sin
  error) -- `executions`/`errors` cuentan todas; `aciertos`/`comparables`/`avg_duration_ms` solo las
  exitosas (C20: el ratio de acierto no debe mezclarse con las filas caídas, pero el recuento de
  ejecuciones/errores sí debe verlas, si no un motor que falla siempre parecería no haberse
  ejecutado nunca).

Mismo patrón `SECURITY DEFINER` ya auditado en 0012/0019/0028/0031 (owner `autoken_definer`,
`SET search_path = pg_catalog, pg_temp`, `REVOKE ALL FROM PUBLIC` + `GRANT EXECUTE TO autoken_app`):
un `platform_admin` no tiene tenant (S1.3), así que una consulta bajo RLS normal vería 0 filas de
todos los tenants -- la agregación cruzando tenants vive aquí, nunca en una consulta Python bajo RLS
(C19: además, ninguna de las dos funciones acepta ningún parámetro que dispare una llamada real a un
proveedor de IA, son de solo lectura sobre datos ya persistidos).

`ratio` cuando `comparables = 0` (un grupo/combinación sin ningún dato comparable, p. ej. todas las
filas fallidas o sin ese campo comparable en absoluto) es `NULL`, nunca `0.0` -- mismo criterio
anti-alucinación que el resto del proyecto: "sin datos todavía" no es lo mismo que "0% de acierto
real" (spec §2, "campo no comparable... no puntúa a favor ni en contra"), y conflacionarlos
impediría al consumidor (frontend, tarea posterior) distinguirlos. `NULLIF(comparables, 0)` en el
denominador ya produce `NULL` de forma natural sin necesidad de ningún `COALESCE` que lo esconda.

Revision ID: 0032_benchmark_field_ranking
Revises: 0031_ocr_benchmark_batch_definer
Create Date: 2026-08-11
"""

from __future__ import annotations

from alembic import op

revision = "0032_benchmark_field_ranking"
down_revision = "0031_ocr_benchmark_batch_definer"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"

# Mapeo campo escalar de `field_results` -> grupo de campo visible (spec §2). `net_amount`/
# `tax_amount`/`total_amount` comparten el grupo "Importes"; el resto tiene grupo propio.
_FIELD_GROUP_CASE = """
    CASE fe->>'field'
        WHEN 'counterparty_tax_id' THEN 'CIF/NIF'
        WHEN 'counterparty_name' THEN 'Nombre'
        WHEN 'invoice_number' THEN 'Nº factura'
        WHEN 'issue_date' THEN 'Fecha'
        WHEN 'total_amount' THEN 'Importes'
        WHEN 'net_amount' THEN 'Importes'
        WHEN 'tax_amount' THEN 'Importes'
    END
"""


def upgrade() -> None:
    # Ambas funciones solo necesitan estas columnas de `ocr_benchmark_results`: mínimo privilegio,
    # mismo criterio que el resto de `GRANT SELECT (columnas)` del proyecto.
    op.execute(
        f"GRANT SELECT (variant, engine, field_results, tax_lines_matched, error, "
        f"aciertos, comparables, duration_ms) "
        f"ON public.ocr_benchmark_results TO {_DEFINER_ROLE}"
    )

    op.execute(
        f"""
        CREATE FUNCTION public.ocr_benchmark_field_group_ranking()
        RETURNS TABLE (
            field_group text,
            variant text,
            engine text,
            aciertos bigint,
            comparables bigint,
            ratio double precision
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            WITH scalar_fields AS (
                SELECT
                    r.variant,
                    r.engine,
                    {_FIELD_GROUP_CASE} AS field_group,
                    (fe->>'match')::boolean AS match
                FROM public.ocr_benchmark_results r
                CROSS JOIN LATERAL jsonb_array_elements(r.field_results) AS fe
                WHERE r.error IS NULL
            ),
            tax_lines AS (
                SELECT
                    r.variant,
                    r.engine,
                    'Tramos IVA' AS field_group,
                    r.tax_lines_matched AS match
                FROM public.ocr_benchmark_results r
                WHERE r.error IS NULL
            ),
            unified AS (
                SELECT field_group, variant, engine, match FROM scalar_fields
                WHERE field_group IS NOT NULL
                UNION ALL
                SELECT field_group, variant, engine, match FROM tax_lines
            )
            SELECT
                field_group,
                variant,
                engine,
                COUNT(*) FILTER (WHERE match IS TRUE) AS aciertos,
                COUNT(*) FILTER (WHERE match IS NOT NULL) AS comparables,
                COUNT(*) FILTER (WHERE match IS TRUE)::float
                    / NULLIF(COUNT(*) FILTER (WHERE match IS NOT NULL), 0) AS ratio
            FROM unified
            GROUP BY field_group, variant, engine
            ORDER BY field_group, ratio DESC
        $$;
        """
    )
    op.execute(
        f"ALTER FUNCTION public.ocr_benchmark_field_group_ranking() OWNER TO {_DEFINER_ROLE}"
    )
    op.execute("REVOKE ALL ON FUNCTION public.ocr_benchmark_field_group_ranking() FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.ocr_benchmark_field_group_ranking() TO {_APP_ROLE}"
    )

    op.execute(
        """
        CREATE FUNCTION public.ocr_benchmark_combination_summary()
        RETURNS TABLE (
            variant text,
            engine text,
            executions bigint,
            errors bigint,
            aciertos bigint,
            comparables bigint,
            avg_duration_ms double precision
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT
                variant,
                engine,
                COUNT(*) AS executions,
                COUNT(*) FILTER (WHERE error IS NOT NULL) AS errors,
                COALESCE(SUM(aciertos) FILTER (WHERE error IS NULL), 0) AS aciertos,
                COALESCE(SUM(comparables) FILTER (WHERE error IS NULL), 0) AS comparables,
                AVG(duration_ms) FILTER (WHERE error IS NULL) AS avg_duration_ms
            FROM public.ocr_benchmark_results
            GROUP BY variant, engine
            ORDER BY variant, engine
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.ocr_benchmark_combination_summary() OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.ocr_benchmark_combination_summary() FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.ocr_benchmark_combination_summary() TO {_APP_ROLE}"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.ocr_benchmark_combination_summary()")
    op.execute("DROP FUNCTION IF EXISTS public.ocr_benchmark_field_group_ranking()")
    op.execute(
        f"REVOKE SELECT (variant, engine, field_results, tax_lines_matched, error, "
        f"aciertos, comparables, duration_ms) "
        f"ON public.ocr_benchmark_results FROM {_DEFINER_ROLE}"
    )
