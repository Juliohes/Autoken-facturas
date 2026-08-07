"""Modelo ORM de `platform_settings` (S4.10, migración 0017).

Tabla de una sola fila (`id boolean PRIMARY KEY DEFAULT true CHECK (id)`, garantiza que nunca
pueda existir una segunda). El código de aplicación no la toca directamente (siempre a través de
las funciones `SECURITY DEFINER` `get_platform_settings`/`set_platform_settings`, ver
`settings_repository.py`); este modelo existe solo para que el esquema declarado coincida con el
de la migración (guard de deriva ORM<->migración, CI).
"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class PlatformSettings(Base):
    __tablename__ = "platform_settings"
    # Mismo `CHECK (id)` que declara la migración 0017 (nunca puede existir una segunda fila):
    # sin declararlo aquí, el guard de deriva ORM<->migración lo detecta como constraint de sobra.
    __table_args__ = (CheckConstraint("id", name="platform_settings_id_check"),)

    id: Mapped[bool] = mapped_column(Boolean, primary_key=True, server_default="true")
    ocr_experiment_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
