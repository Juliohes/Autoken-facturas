"""Campos estructurados de IRPF en la extracción OCR.

El IRPF es una retención distinta del IVA y necesita conservarse separada desde la lectura hasta la
revisión. Los campos son opcionales porque la mayoría de facturas no llevan retención.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040_ocr_irpf_fields"
down_revision = "0039_recoverable_ocr_intake"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ocr_extractions", sa.Column("irpf_rate", sa.Numeric(), nullable=True))
    op.add_column("ocr_extractions", sa.Column("irpf_amount", sa.Numeric(), nullable=True))


def downgrade() -> None:
    op.drop_column("ocr_extractions", "irpf_amount")
    op.drop_column("ocr_extractions", "irpf_rate")
