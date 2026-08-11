"""Tests de comportamiento S6.7 C1 (spec docs/specs/S6.7-benchmark-real-motor-variante.md):
confirmar una factura encola el benchmark en segundo plano, sin bloquear la respuesta.

Unit de wiring, no de extremo a extremo contra Redis real (eso ya lo cubre el smoke test genérico
`test_ocr_worker_wiring.py`): aquí solo se verifica que `invoicing.service.confirm` llama a
`jobs.queue.enqueue_ocr_benchmark` con los ids correctos, igual que ya se prueba el encolado de OCR
en la subida (S2.1/S2.3). El resto del motor (C2-C9) ya está cubierto en `test_ocr_benchmark.py`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from tests._invoicing import auth, confirm_body, confirm_url, seed_confirmable
from tests._ocr import set_ocr_experiment_enabled

Api = tuple[object, dict[str, str]]


async def test_c1_confirmar_una_factura_encola_el_benchmark_sin_bloquear_la_respuesta(
    authapi: Api, monkeypatch
) -> None:
    from jobs import queue

    mock_enqueue = AsyncMock()
    monkeypatch.setattr(queue, "enqueue_ocr_benchmark", mock_enqueue)
    client, dsns = authapi
    s = await seed_confirmable(dsns, client)

    resp = await client.post(
        confirm_url(s["file_id"]), headers=auth(s["token"]), json=confirm_body()
    )

    assert resp.status_code == 201, resp.text
    mock_enqueue.assert_awaited_once_with(s["tenant_id"], s["company_id"], s["file_id"])


async def test_interruptor_apagado_no_construye_los_motores_reales_de_benchmark(
    authapi: Api, monkeypatch
) -> None:
    """S6.7 auditoría 2026-08-11, hallazgo ALTO: con el interruptor apagado,
    `run_ocr_benchmark_task` NO debe construir los 6 motores reales en absoluto -- la comprobación
    del interruptor tiene que ser lo PRIMERO que se ejecuta en este camino, antes de
    `build_named_ranking_extractors` (mismo criterio ya corregido dos veces en el proyecto, S4.8 y
    S2.10, para el mismo tipo de riesgo)."""
    from jobs import ocr_benchmark

    client, dsns = authapi
    await set_ocr_experiment_enabled(dsns, False)
    s = await seed_confirmable(dsns, client)

    build_mock = MagicMock()
    monkeypatch.setattr(ocr_benchmark, "build_named_ranking_extractors", build_mock)

    await ocr_benchmark.run_ocr_benchmark_task({}, s["tenant_id"], s["company_id"], s["file_id"])

    build_mock.assert_not_called()
