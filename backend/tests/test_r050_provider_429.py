"""Prueba de comportamiento del proveedor OCR limitado por cuota (R-050/R-045)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncpg
import pytest

from invoice_intake.constants import FileStatus
from ocr.extraction import InvoiceExtractionError
from ocr.policy import OcrPolicy
from shared.metrics import is_provider_rate_limited, ocr_provider_429_total
from tests._auth import USER_PASSWORD_HASH
from tests._dbtest import seed_company, seed_membership, seed_tenant, seed_user
from tests._ocr import build_extracted, make_extractor, run_ocr, seed_uploaded_file


class ProviderRateLimitedError(RuntimeError):
    """Error falso del proveedor con el atributo que normalizan los adaptadores reales."""

    status_code = 429


async def _seed(dsns: dict[str, str]) -> tuple[str, str, str]:
    tenant_id = await seed_tenant(dsns["admin"], "provider-429", "Proveedor 429")
    user_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="ana@provider-429.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Mi Empresa", cif="B06183446"
    )
    await seed_membership(
        dsns["admin"], user_id=user_id, company_id=company_id, tenant_id=tenant_id
    )
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=user_id
    )
    return tenant_id, company_id, file_id


@pytest.mark.asyncio
async def test_429_del_primario_activa_fallback_y_no_guarda_el_error(authapi, monkeypatch) -> None:
    """Un 429 no pierde la factura si el fallback puede completar la lectura."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns)

    import jobs.ocr as ocr_job

    policy = OcrPolicy(
        version=1,
        primary_engine="fake-primary",
        primary_model="fake-primary-v1",
        fallback_enabled=True,
        fallback_engine="fake-fallback",
        fallback_model="fake-fallback-v1",
        consensus_mode="primary_only",
    )

    async def policy_for_test(_settings, _session, _tenant_id):
        return policy

    monkeypatch.setattr(ocr_job, "_get_production_policy", policy_for_test)
    monkeypatch.setattr(
        ocr_job,
        "build_fallback_extractor",
        lambda _settings, _policy: make_extractor(build_extracted()),
    )

    metric = ocr_provider_429_total.labels(
        engine=policy.primary_engine, model=policy.primary_model
    )
    before = metric._value.get()
    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(error=ProviderRateLimitedError("provider raw secret")),
    )

    conn = await asyncpg.connect(dsns["admin"])
    try:
        status = await conn.fetchval("SELECT status FROM uploaded_files WHERE id = $1", file_id)
        extraction = await conn.fetchrow(
            "SELECT raw FROM ocr_extractions WHERE uploaded_file_id = $1", file_id
        )
    finally:
        await conn.close()

    assert status == FileStatus.OCR_DONE.value
    assert extraction is not None
    raw = extraction["raw"]
    assert raw in ({}, "{}")
    assert "provider raw secret" not in str(raw)
    assert metric._value.get() == before + 1


@pytest.mark.asyncio
async def test_adaptador_gemini_conserva_un_429_del_sdk_en_la_causa(monkeypatch) -> None:
    """Un SDK que expone solo status_code=429 mantiene la clasificación del worker."""
    import ocr.engines.gemini as gemini
    from ocr.engines.gemini_extractor import GeminiInvoiceExtractor

    class RateLimitedSdkError(RuntimeError):
        status_code = 429

    client = SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(
                generate_content=AsyncMock(side_effect=RateLimitedSdkError("cuota agotada"))
            )
        )
    )

    class FakeGeminiEngine:
        def __init__(self, **_kwargs) -> None:
            pass

        def ensure_client(self):
            return client

    monkeypatch.setattr(gemini, "GeminiEngine", FakeGeminiEngine)
    extractor = GeminiInvoiceExtractor(
        engine="gemini-3.5-flash",
        model="gemini-3.5-flash",
        project=None,
        location="global",
        credentials_path=None,
    )

    with pytest.raises(InvoiceExtractionError) as error:
        await extractor.extract(b"synthetic", "image/jpeg")

    assert is_provider_rate_limited(error.value)
