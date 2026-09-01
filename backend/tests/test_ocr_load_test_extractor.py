"""Comportamiento del extractor OCR determinista exclusivo de carga R-050."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from ocr.engines.production import build_production_extractor
from ocr.extraction import DocumentPage
from ocr.policy import OcrPolicy
from shared.config import AppEnv


def test_load_test_usa_un_extractor_determinista_sin_llamar_a_un_proveedor() -> None:
    settings = SimpleNamespace(app_env=AppEnv.LOAD_TEST)
    policy = OcrPolicy(
        version=1,
        primary_engine="gemini-3.5-flash",
        primary_model="gemini-3.5-flash",
        fallback_enabled=False,
        consensus_mode="primary_only",
    )

    extractor = build_production_extractor(settings, policy)
    invoice = asyncio.run(
        extractor.extract_pages([DocumentPage(b"synthetic", "image/jpeg")])  # type: ignore[attr-defined]
    )

    assert invoice.engine == "load-test"
    assert invoice.model == "deterministic"
    assert invoice.invoice_number == "R050-SYNTHETIC"
    assert invoice.total_amount == 121
