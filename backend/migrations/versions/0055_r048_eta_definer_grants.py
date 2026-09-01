"""Corrige los permisos del rol definidor de las muestras ETA (R-048)."""

from __future__ import annotations

from alembic import op

revision = "0055_r048_eta_definer_grants"
down_revision = "0054_r013_capture_session"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Permite a la función SECURITY DEFINER insertar y purgar muestras, sin exponer la tabla."""
    op.execute("GRANT SELECT, INSERT, DELETE ON public.ocr_processing_samples TO autoken_definer")
    op.execute(
        "GRANT USAGE, SELECT ON SEQUENCE public.ocr_processing_samples_id_seq TO autoken_definer"
    )


def downgrade() -> None:
    op.execute(
        "REVOKE USAGE, SELECT ON SEQUENCE public.ocr_processing_samples_id_seq FROM autoken_definer"
    )
    op.execute(
        "REVOKE SELECT, INSERT, DELETE ON public.ocr_processing_samples FROM autoken_definer"
    )
