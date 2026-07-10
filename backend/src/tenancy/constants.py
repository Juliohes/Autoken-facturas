"""Constantes de dominio compartidas del núcleo de tenancy (roles y estados de usuario).

Fuente única de los literales de `role` y `status` de `users`, para que ni el modelo ORM
(`tenancy/models.py`) ni la autenticación (`identity`) los re-hardcodeen. Son `StrEnum`: cada
miembro es un `str` (comparable e intercambiable con el texto que guarda la BD), pero con nombre
simbólico y conjunto cerrado.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Rol de un usuario. Decide el alcance; el CHECK de `users` lo restringe a este conjunto."""

    PLATFORM_ADMIN = "platform_admin"
    TENANT_ADMIN = "tenant_admin"
    USER = "user"


class UserStatus(StrEnum):
    """Estado de aprobación de un usuario. La transición `pending`->`active` es gate de S1.4."""

    PENDING = "pending"
    ACTIVE = "active"


class CompanyStatus(StrEnum):
    """Estado de una empresa. El CHECK de `companies` (migración 0001) lo restringe a este conjunto.

    `pending` la crea un registro autoservicio (S1.4) hasta que el `tenant_admin` la aprueba;
    `active` es el estado de las empresas dadas de alta o importadas por el admin.
    """

    ACTIVE = "active"
    PENDING = "pending"
