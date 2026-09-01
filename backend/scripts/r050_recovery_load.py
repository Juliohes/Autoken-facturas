"""Lanzador de una oleada R-050 para interrumpir Redis durante el tráfico.

Se ejecuta en segundo plano mientras el operador detiene y vuelve a arrancar Redis. El JSON solo
contiene conteos HTTP y no guarda tokens, correos ni IDs de documentos.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

from r050_load_test import _jpeg_bytes, _load_config, _login


async def run(
    config_path: Path,
    stagger_seconds: float,
    pause_after_login: float,
    ready_file: Path | None,
) -> dict[str, Any]:
    config = _load_config(config_path)
    limits = httpx.Limits(max_connections=120, max_keepalive_connections=20)
    async with httpx.AsyncClient(base_url=config.base_url, limits=limits, timeout=30) as client:
        tokens = tuple(await asyncio.gather(*(_login(client, config, user) for user in config.users)))
        if ready_file is not None:
            ready_file.parent.mkdir(parents=True, exist_ok=True)
            ready_file.write_text("ready\n", encoding="utf-8")
        if pause_after_login:
            await asyncio.sleep(pause_after_login)
        async def upload(index: int) -> int | str:
            user_index, invoice_index = divmod(index, config.uploads_per_user)
            user = config.users[user_index]
            if stagger_seconds:
                await asyncio.sleep(index * stagger_seconds)
            try:
                response = await client.post(
                    "/api/v1/uploads",
                    headers={
                        "Host": config.tenant_host,
                        "Authorization": f"Bearer {tokens[user_index]}",
                    },
                    files={
                        "file": (
                            f"r050-recovery-{index}.jpg",
                            _jpeg_bytes(1000 + index),
                            "image/jpeg",
                        )
                    },
                    data={"company_id": user.company_id, "direction": "recibida"},
                )
                return response.status_code
            except httpx.HTTPError as exc:
                return type(exc).__name__

        results = await asyncio.gather(
            *(upload(index) for index in range(len(config.users) * config.uploads_per_user))
        )
    counts = Counter(str(result) for result in results)
    return {
        "requested": len(results),
        "status_codes": dict(sorted(counts.items())),
        "accepted_201": counts.get("201", 0),
        "transport_errors": sum(value for key, value in counts.items() if not key.isdigit()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stagger-seconds", type=float, default=0.0)
    parser.add_argument("--pause-after-login", type=float, default=0.0)
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()
    report = asyncio.run(
        run(args.config, args.stagger_seconds, args.pause_after_login, args.ready_file)
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
