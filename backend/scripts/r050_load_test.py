"""Arnés reproducible de carga y recuperación de OCR para R-050.

No crea usuarios ni empresas y no contiene credenciales. Recibe un JSON de staging con diez
usuarios de prueba ya preparados, sube diez imágenes distintas por usuario y genera un informe sin
PII. El worker OCR debe apuntar a un proveedor de prueba o estar desactivado según el escenario.

Uso desde `backend/`:

    python scripts/r050_load_test.py --config /ruta/r050.json --out /ruta/r050-report.json

Formato mínimo del JSON:

    {
      "base_url": "http://127.0.0.1:8000",
      "tenant_host": "load.localhost",
      "users": [
        {"email": "load-01@example.test", "password": "...", "company_id": "..."}
      ]
    }

El fichero de configuración es local y no debe versionarse.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

_UPLOADS = "/api/v1/uploads"
_METRICS = "/api/v1/metrics"
_TERMINAL_STATUSES = frozenset({"ocr_done", "needs_review", "ocr_failed", "capture_unreadable"})
_PENDING_STATUSES = frozenset({"pending_ocr", "processing"})


@dataclass(frozen=True)
class LoadUser:
    email: str
    password: str
    company_id: str


@dataclass(frozen=True)
class LoadConfig:
    base_url: str
    tenant_host: str
    users: tuple[LoadUser, ...]
    uploads_per_user: int = 10
    poll_timeout_seconds: float = 180.0


@dataclass(frozen=True)
class UploadResult:
    user_index: int
    file_id: str | None
    status_code: int
    latency_seconds: float


def _percentile(values: list[float], percentile: float) -> float | None:
    """Percentil interpolado, sin depender de una librería estadística externa."""
    if not values:
        return None
    if not 0 <= percentile <= 100:
        raise ValueError("percentile debe estar entre 0 y 100")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _recovery_snapshot(metrics: dict[str, float | None]) -> dict[str, float | None]:
    """Extrae el estado operativo necesario para comprobar recuperación, sin PII."""
    return {
        "queue_backend_up": metrics.get("autoken_ocr_queue_backend_up"),
        "queue_depth": metrics.get("autoken_ocr_queue_depth"),
        "pending": metrics.get('autoken_ocr_documents{state="pending"}'),
        "processing": metrics.get('autoken_ocr_documents{state="processing"}'),
        "abandoned": metrics.get('autoken_ocr_documents{state="abandoned"}'),
        "failed": metrics.get('autoken_ocr_documents{state="failed"}'),
        "expired_pending": metrics.get("autoken_expired_pending_count"),
    }


def _recovery_delta(
    before: dict[str, float | None], after: dict[str, float | None]
) -> dict[str, float | None]:
    """Compara la recuperación final con la línea base global del stack."""
    before_snapshot = _recovery_snapshot(before)
    after_snapshot = _recovery_snapshot(after)
    delta: dict[str, float | None] = {}
    for key, after_value in after_snapshot.items():
        before_value = before_snapshot[key]
        if before_value is None or after_value is None:
            delta[key] = None
        else:
            delta[key] = after_value - before_value
    return delta


def _load_config(path: Path) -> LoadConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    users = tuple(LoadUser(**user) for user in raw["users"])
    if len(users) != 10:
        raise ValueError("R-050 requiere exactamente 10 usuarios")
    uploads_per_user = int(raw.get("uploads_per_user", 10))
    if uploads_per_user != 10:
        raise ValueError("R-050 requiere exactamente 10 uploads por usuario")
    return LoadConfig(
        base_url=raw["base_url"],
        tenant_host=raw["tenant_host"],
        users=users,
        uploads_per_user=uploads_per_user,
        poll_timeout_seconds=float(raw.get("poll_timeout_seconds", 180.0)),
    )


def _jpeg_bytes(seed: int) -> bytes:
    """Genera un JPEG válido y distinto para no activar la deduplicación por SHA-256."""
    image = Image.new("RGB", (100, 60), (seed % 255, (seed * 3) % 255, (seed * 7) % 255))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=85)
    return output.getvalue()


async def _login(client: httpx.AsyncClient, config: LoadConfig, user: LoadUser) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": user.password},
        headers={"Host": config.tenant_host},
    )
    if response.status_code != 200:
        raise RuntimeError(f"login de usuario de carga rechazado: HTTP {response.status_code}")
    body = response.json()
    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("login de usuario de carga no devolvió access_token")
    return token


async def _upload(
    client: httpx.AsyncClient,
    config: LoadConfig,
    user: LoadUser,
    token: str,
    user_index: int,
    invoice_index: int,
) -> UploadResult:
    started = time.perf_counter()
    response = await client.post(
        _UPLOADS,
        headers={"Host": config.tenant_host, "Authorization": f"Bearer {token}"},
        files={
            "file": (
                f"r050-{user_index}-{invoice_index}.jpg",
                _jpeg_bytes(user_index * 100 + invoice_index),
                "image/jpeg",
            )
        },
        data={"company_id": user.company_id, "direction": "recibida"},
    )
    body = (
        response.json()
        if response.headers.get("content-type", "").startswith("application/json")
        else {}
    )
    return UploadResult(
        user_index=user_index,
        file_id=body.get("id") if response.status_code == 201 else None,
        status_code=response.status_code,
        latency_seconds=time.perf_counter() - started,
    )


async def _status(
    client: httpx.AsyncClient, config: LoadConfig, token: str, file_id: str
) -> tuple[str, int]:
    response = await client.get(
        f"/api/v1/uploads/{file_id}/status",
        headers={"Host": config.tenant_host, "Authorization": f"Bearer {token}"},
    )
    if response.status_code != 200:
        return "http_error", response.status_code
    return str(response.json().get("status", "unknown")), response.status_code


async def _wait_for_ocr(
    client: httpx.AsyncClient,
    config: LoadConfig,
    tokens: tuple[str, ...],
    uploads: list[UploadResult],
) -> dict[str, int]:
    pending = {
        result.file_id: result.user_index for result in uploads if result.file_id is not None
    }
    final_statuses: dict[str, str] = {}
    deadline = time.monotonic() + config.poll_timeout_seconds
    while pending and time.monotonic() < deadline:
        pending_items = tuple(pending.items())
        current = await asyncio.gather(
            *(
                _status(client, config, tokens[user_index], file_id)
                for file_id, user_index in pending_items
            )
        )
        for (file_id, _user_index), (status, _code) in zip(pending_items, current, strict=True):
            final_statuses[file_id] = status
            if status in _TERMINAL_STATUSES or status == "http_error":
                pending.pop(file_id, None)
        if pending:
            await asyncio.sleep(1)
    if pending:
        for file_id in pending:
            final_statuses[file_id] = "poll_timeout"
    statuses: dict[str, int] = {}
    for status in final_statuses.values():
        statuses[status] = statuses.get(status, 0) + 1
    return statuses


async def _check_inbox_privacy(
    client: httpx.AsyncClient,
    config: LoadConfig,
    tokens: tuple[str, ...],
    uploads: list[UploadResult],
) -> tuple[int, int]:
    own_ids: dict[int, set[str]] = {index: set() for index in range(len(tokens))}
    for upload in uploads:
        if upload.file_id is not None:
            own_ids[upload.user_index].add(upload.file_id)
    leaks = 0
    http_errors = 0
    for user_index, token in enumerate(tokens):
        response = await client.get(
            "/api/v1/invoices/inbox",
            headers={"Host": config.tenant_host, "Authorization": f"Bearer {token}"},
        )
        if response.status_code != 200:
            http_errors += 1
            continue
        visible = {str(item["id"]) for item in response.json().get("items", [])}
        leaks += len(visible - own_ids[user_index])
    return leaks, http_errors


async def _metrics(client: httpx.AsyncClient, config: LoadConfig) -> dict[str, float | None]:
    response = await client.get(_METRICS)
    if response.status_code != 200:
        return {}
    wanted = {
        "autoken_db_pool_size",
        "autoken_db_pool_checked_out",
        "autoken_db_pool_overflow",
        "autoken_db_pool_capacity",
        "autoken_upload_phase_seconds_count",
        "autoken_upload_phase_seconds_sum",
        "autoken_ocr_queue_depth",
        "autoken_ocr_queue_backend_up",
        "autoken_ocr_documents",
        "autoken_expired_pending_count",
        "autoken_ocr_provider_429_total",
    }
    result: dict[str, float | None] = {}
    for line in response.text.splitlines():
        name, separator, raw_value = line.partition(" ")
        metric_name = name.split("{", 1)[0]
        if separator and metric_name in wanted and not name.startswith("#"):
            try:
                value = float(raw_value)
                result[metric_name] = (result.get(metric_name, 0) or 0) + value
                if "{" in name:
                    result[name] = value
            except ValueError:
                continue
    return result


async def run(config: LoadConfig) -> dict[str, Any]:
    limits = httpx.Limits(max_connections=120, max_keepalive_connections=20)
    async with httpx.AsyncClient(base_url=config.base_url, limits=limits, timeout=30) as client:
        metrics_before = await _metrics(client, config)
        tokens = tuple(
            await asyncio.gather(*(_login(client, config, user) for user in config.users))
        )
        uploads = list(
            await asyncio.gather(
                *(
                    _upload(client, config, user, tokens[user_index], user_index, invoice_index)
                    for user_index, user in enumerate(config.users)
                    for invoice_index in range(config.uploads_per_user)
                )
            )
        )
        status_counts = await _wait_for_ocr(client, config, tokens, uploads)
        leaks, inbox_http_errors = await _check_inbox_privacy(client, config, tokens, uploads)
        metrics = await _metrics(client, config)
    latencies = [result.latency_seconds for result in uploads]
    status_codes: dict[str, int] = {}
    for result in uploads:
        status_codes[str(result.status_code)] = status_codes.get(str(result.status_code), 0) + 1
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "scenario": {"users": len(config.users), "uploads_per_user": config.uploads_per_user},
        "uploads": {
            "requested": len(uploads),
            "status_codes": status_codes,
            "p50_seconds": _percentile(latencies, 50),
            "p95_seconds": _percentile(latencies, 95),
            "mean_seconds": statistics.fmean(latencies) if latencies else None,
        },
        "ocr_status_counts": status_counts,
        "metrics_before": metrics_before,
        "metrics_snapshot": metrics,
        "recovery_before": _recovery_snapshot(metrics_before),
        "recovery": _recovery_snapshot(metrics),
        "recovery_delta": _recovery_delta(metrics_before, metrics),
        "rate_limit_429": status_codes.get("429", 0),
        "provider_429": metrics.get("autoken_ocr_provider_429_total"),
        "cross_user_leaks": leaks,
        "inbox_http_errors": inbox_http_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(run(_load_config(args.config)))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return (
        0
        if report["uploads"]["status_codes"].get("201", 0) == 100
        and report["cross_user_leaks"] == 0
        and report["inbox_http_errors"] == 0
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
