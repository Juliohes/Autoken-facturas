"""Preflight seguro para el canario R-051.

Lee el entorno ya inyectado por el despliegue, valida flags y allowlist, y comprueba que los
secretos obligatorios de staging existen sin imprimir nunca sus valores.

Uso desde ``backend/``::

    python scripts/r051_canary_preflight.py --json

El código de salida es 0 solo cuando el entorno está listo para iniciar el canario.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from shared.rollout import FeatureFlag

CheckStatus = Literal["ok", "error", "warning"]

_REQUIRED_SECRET_NAMES = (
    "GRAFANA_ADMIN_PASSWORD",
    "DB_ENCRYPTION_MASTER_KEY",
    "POSTGRES_APP_PASSWORD",
)
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    status: CheckStatus
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass(frozen=True)
class PreflightReport:
    ready: bool
    checks: tuple[PreflightCheck, ...]

    def to_dict(self) -> dict[str, object]:
        return {"ready": self.ready, "checks": [check.to_dict() for check in self.checks]}


def _check_feature_flags(environment: Mapping[str, str]) -> PreflightCheck:
    invalid: list[str] = []
    defaulted: list[str] = []
    for flag in FeatureFlag:
        name = flag.value.upper()
        raw = environment.get(name)
        if raw is None:
            defaulted.append(name)
            continue
        normalized = raw.strip().lower()
        if normalized not in _TRUE_VALUES and normalized not in _FALSE_VALUES:
            invalid.append(name)
    if invalid:
        return PreflightCheck(
            "feature_flags",
            "error",
            f"valores booleanos inválidos: {', '.join(invalid)}",
        )
    if defaulted:
        return PreflightCheck(
            "feature_flags",
            "warning",
            f"usan el default compatible: {', '.join(defaulted)}",
        )
    return PreflightCheck("feature_flags", "ok", f"{len(tuple(FeatureFlag))} flags válidos")


def _check_tenant_allowlist(environment: Mapping[str, str]) -> PreflightCheck:
    raw = environment.get("ROLLOUT_TENANT_ALLOWLIST", "[]")
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return PreflightCheck("tenant_allowlist", "error", "no es JSON válido")
    if not isinstance(values, list):
        return PreflightCheck("tenant_allowlist", "error", "debe ser una lista JSON")
    try:
        tuple(UUID(str(value)) for value in values)
    except (ValueError, TypeError):
        return PreflightCheck("tenant_allowlist", "error", "contiene un tenant UUID inválido")
    return PreflightCheck(
        "tenant_allowlist",
        "ok",
        "global" if not values else f"{len(values)} tenant(s) piloto",
    )


def _check_staging_secrets(environment: Mapping[str, str]) -> PreflightCheck:
    missing = [name for name in _REQUIRED_SECRET_NAMES if not environment.get(name, "").strip()]
    if missing:
        return PreflightCheck(
            "staging_secrets",
            "error",
            f"faltan variables requeridas: {', '.join(missing)}",
        )
    return PreflightCheck("staging_secrets", "ok", "variables requeridas presentes")


def preflight_environment(environment: Mapping[str, str]) -> PreflightReport:
    """Evalúa un entorno sin devolver secretos ni valores de configuración sensible."""
    checks = (
        _check_feature_flags(environment),
        _check_tenant_allowlist(environment),
        _check_staging_secrets(environment),
    )
    return PreflightReport(
        ready=all(check.status == "ok" for check in checks),
        checks=checks,
    )


def _read_env_file(path: Path) -> dict[str, str]:
    """Lee el subconjunto simple de dotenv usado por el Compose, sin mostrar valores."""
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"línea {line_number} sin separador '='")
        name, value = line.split("=", 1)
        name = name.strip()
        if not name or not name.replace("_", "").isalnum():
            raise ValueError(f"nombre inválido en línea {line_number}")
        values[name] = value.strip().strip('"').strip("'")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emite el informe como JSON")
    parser.add_argument(
        "--env-file",
        type=Path,
        help="fichero dotenv a validar; las variables del proceso tienen prioridad",
    )
    args = parser.parse_args()
    environment = dict(_read_env_file(args.env_file)) if args.env_file else {}
    environment.update(os.environ)
    report = preflight_environment(environment)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=True))
    else:
        print(f"R-051 canary ready: {'yes' if report.ready else 'no'}")
        for check in report.checks:
            print(f"[{check.status}] {check.name}: {check.detail}")
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
