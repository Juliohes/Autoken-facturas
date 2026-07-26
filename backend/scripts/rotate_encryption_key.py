"""CLI de la rotación de la clave maestra de cifrado en reposo (S5.2 C9).

Re-cifra TODO el histórico (todos los tenants) con una clave maestra nueva. Operación de
mantenimiento explícita, nunca automática (spec §2 "Rotación de clave"): la clave vieja es la que ya
usa la app (`DB_ENCRYPTION_MASTER_KEY`/`settings.db_encryption_master_key`); la nueva se pasa
SIEMPRE por la env var `DB_ENCRYPTION_MASTER_KEY_NEW`, nunca por un argumento de línea de comandos
(hallazgo de auditoría: un argumento de CLI queda visible en `ps`/el historial de shell de cualquier
usuario con acceso al VPS; una env var exportada en el propio proceso, no). Tras una ejecución con
éxito, el operador debe:
  1. Verificar el resumen (0 fallidos).
  2. Actualizar `DB_ENCRYPTION_MASTER_KEY` en el `.env` del VPS con la clave nueva.
  3. Reiniciar la app (para que lea la clave nueva).
La clave vieja deja de descifrar nada en cuanto termina la rotación: guardarla hasta confirmar el
reinicio, por si hace falta reintentar un tenant que falló.

Reanudable (spec §5): un tenant ya rotado se detecta y se salta; basta con volver a lanzar el mismo
comando con las mismas dos claves.

Uso (desde `backend/`, con el venv activado):
    DB_ENCRYPTION_MASTER_KEY_NEW="<clave nueva>" python scripts/rotate_encryption_key.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from jobs.key_rotation import rotate_all_tenants
from shared.config import get_settings


def main() -> None:
    new_master_key = os.environ.get("DB_ENCRYPTION_MASTER_KEY_NEW")
    if not new_master_key:
        print("Falta la clave nueva: exporta DB_ENCRYPTION_MASTER_KEY_NEW.", file=sys.stderr)
        raise SystemExit(2)
    old_master_key = get_settings().db_encryption_master_key
    if new_master_key == old_master_key:
        print("La clave nueva es IGUAL a la vigente: nada que rotar.", file=sys.stderr)
        raise SystemExit(2)

    summary = asyncio.run(rotate_all_tenants(old_master=old_master_key, new_master=new_master_key))
    print(
        f"Rotación: {summary.tenants_total} tenants, {summary.rotated} rotados ahora, "
        f"{summary.already_done} ya estaban rotados, {summary.empty} sin datos que rotar."
    )
    failed = summary.tenants_total - summary.rotated - summary.already_done - summary.empty
    if failed:
        print(
            f"{failed} tenant(s) fallaron durante la rotación "
            f"(ver logs, key_rotation.tenant_failed) — relanza el mismo comando para "
            f"reintentarlos, los ya rotados se saltan.",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
