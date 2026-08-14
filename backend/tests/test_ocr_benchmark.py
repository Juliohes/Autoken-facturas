"""Tests de comportamiento S6.7 Área A/B (motor de ejecución real), spec
docs/specs/S6.7-benchmark-real-motor-variante.md, C2-C4, C9, C23 (C1 -- enganche a confirmar -- se
prueba aparte, más ligero, en `test_invoice_confirm.py`; C5-C8 ya cubiertos por
`test_ocr_benchmark_scoring.py`, aquí no se repiten).

Postgres real, con dobles de extractor inyectados (nunca se llama a ningún proveedor real).
`ocr.benchmark.run_benchmark` es el motor "en vivo" (mismo criterio que `run_ocr_ranking`, S4.8):
`extractors` es OBLIGATORIO, como pares `(engine_name, InvoiceExtractor)` -- así se conoce el
nombre del motor incluso cuando `.extract()` falla (C2 exige guardar una fila de error por motor
caído, a diferencia del ranking actual que solo loguea y salta). Ningún fallback a motores reales:
mismo motivo que el incidente real de coste de S4.8 (ver docstring de `jobs.ocr.run_ocr`).

`own_cif`/`ocr_experiment_enabled` se pasan aquí como parámetros directos de `run_benchmark`
(2026-08-11, S6.7 auditoría, hallazgo de arquitectura): antes `run_benchmark` los resolvía él mismo
consultando `platform_settings`/`companies`, invirtiendo la dirección de dependencias de `ocr`. El
llamador real de producción (`jobs.ocr_benchmark.run_ocr_benchmark_task`) los resuelve en su propia
sesión corta; estos tests, al llamar a `run_benchmark` directamente, hacen lo mismo que ese
llamador.
"""

from __future__ import annotations

import pytest

from tests._dbtest import seed_company, seed_tenant, seed_user
from tests._ocr import (
    OWN_CIF,
    make_extractor,
    real_jpeg_bytes,
    seed_uploaded_file,
)
from tests._ocr_benchmark import (
    count_benchmark_results,
    fetch_benchmark_results,
    fetch_benchmark_results_raw,
)

Api = tuple[object, dict[str, str]]

COUNTERPARTY_CIF = "A39031620"


def _truth(**overrides: object) -> dict[str, object]:
    truth = {
        "counterparty_tax_id": COUNTERPARTY_CIF,
        "counterparty_name": "Proveedor SA",
        "invoice_number": "F-2026-001",
        "issue_date": "2026-05-10",
        "total_amount": "121.00",
        "net_amount": "100.00",
        "tax_amount": "21.00",
        "tax_lines": [{"iva_pct": "21", "base": "100.00", "cuota": "21.00"}],
    }
    truth.update(overrides)
    return truth


async def _seed(dsns: dict[str, str], *, slug: str) -> tuple[str, str, str]:
    tenant_id = await seed_tenant(dsns["admin"], slug, f"{slug.upper()} Asesoría")
    user_id = await seed_user(
        dsns["admin"], tenant_id=tenant_id, email=f"ana@{slug}.es", role="user"
    )
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Mi Empresa", cif=OWN_CIF
    )
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=user_id
    )
    return tenant_id, company_id, file_id


async def test_interruptor_apagado_no_genera_ninguna_fila(authapi: Api) -> None:
    """Mismo criterio que el ranking (S4.8 C1): apagado por defecto, coste cero."""
    from ocr.benchmark import run_benchmark

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, slug="bm-off")

    await run_benchmark(
        tenant_id,
        company_id,
        file_id,
        content=real_jpeg_bytes(),
        content_type="image/jpeg",
        truth=_truth(),
        own_cif=OWN_CIF,
        ocr_experiment_enabled=False,
        extractors=[("gemini-3-flash", make_extractor(_reading_invoice()))],
    )

    assert await count_benchmark_results(dsns, file_id=file_id) == 0


def _reading_invoice(**overrides: object):
    """`ExtractedInvoice` de prueba que produce una lectura perfecta (coincide con `_truth()`)."""
    from tests._ocr import build_extracted

    return build_extracted(
        counterparty_cif=str(overrides.pop("counterparty_tax_id", COUNTERPARTY_CIF)),
        counterparty_name=str(overrides.pop("counterparty_name", "Proveedor SA")),
        invoice_number=str(overrides.pop("invoice_number", "F-2026-001")),
        **overrides,
    )


async def test_c9_genera_una_fila_por_cada_variante_de_un_motor_con_su_desglose_por_campo(
    authapi: Api,
) -> None:
    """spec: C9 -- 3 variantes (original/enhanced/clahe) x 1 motor = 3 filas, cada una con el
    desglose acierto/fallo por campo, no solo el ratio agregado."""
    from ocr.benchmark import run_benchmark

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, slug="bm-c9")

    await run_benchmark(
        tenant_id,
        company_id,
        file_id,
        content=real_jpeg_bytes(),
        content_type="image/jpeg",
        truth=_truth(),
        own_cif=OWN_CIF,
        ocr_experiment_enabled=True,
        extractors=[("gemini-3-flash", make_extractor(_reading_invoice()))],
    )

    results = await fetch_benchmark_results(dsns, file_id=file_id)
    assert len(results) == 3, results
    assert {r["variant"] for r in results} == {"original", "enhanced", "clahe"}
    for row in results:
        assert row["engine"] == "gemini-3-flash"
        assert row["error"] is None
        assert row["comparables"] == 8, row  # 7 campos escalares + tramos de IVA
        assert row["aciertos"] == 8, row
        field_results = row["field_results"]
        assert isinstance(field_results, list) and len(field_results) == 7, field_results
        assert all(f["match"] is True for f in field_results), field_results
        assert row["tax_lines_matched"] is True


async def test_benchmark_multipagina_entrega_el_documento_completo_en_cada_variante(
    authapi: Api,
) -> None:
    """Las tres variantes conservan todas las hojas; no se permite evaluar solo la raíz."""
    from ocr.benchmark import run_benchmark
    from ocr.extraction import DocumentPage

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, slug="bm-multipage")
    observed_pages: list[int] = []

    class PageExtractor:
        async def extract(self, _content: bytes, _content_type: str):
            raise AssertionError("no debe reducirse a una página")

        async def extract_pages(self, pages):
            observed_pages.append(len(pages))
            return _reading_invoice()

    await run_benchmark(
        tenant_id,
        company_id,
        file_id,
        pages=[
            DocumentPage(real_jpeg_bytes(), "image/jpeg"),
            DocumentPage(real_jpeg_bytes(), "image/jpeg"),
        ],
        truth=_truth(),
        own_cif=OWN_CIF,
        ocr_experiment_enabled=True,
        extractors=[("gemini-3-flash", PageExtractor())],
    )

    assert observed_pages == [2, 2, 2]
    assert await count_benchmark_results(dsns, file_id=file_id) == 3


async def test_c2_un_motor_caido_en_una_variante_no_impide_que_los_demas_terminen(
    authapi: Api,
) -> None:
    """spec: C2 -- el motor caído deja fila de error (aciertos=0, comparables=0); el resto sigue."""
    from ocr.benchmark import run_benchmark
    from ocr.extraction import InvoiceExtractionError

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, slug="bm-c2")

    await run_benchmark(
        tenant_id,
        company_id,
        file_id,
        content=real_jpeg_bytes(),
        content_type="image/jpeg",
        truth=_truth(),
        own_cif=OWN_CIF,
        ocr_experiment_enabled=True,
        extractors=[
            ("azure-docintel", make_extractor(error=InvoiceExtractionError("timeout simulado"))),
            ("gemini-3-flash", make_extractor(_reading_invoice())),
        ],
    )

    results = await fetch_benchmark_results(dsns, file_id=file_id)
    assert len(results) == 6, results  # 3 variantes x 2 motores

    failed = [r for r in results if r["engine"] == "azure-docintel"]
    assert len(failed) == 3, failed
    for row in failed:
        assert row["error"] is not None
        assert row["aciertos"] == 0
        assert row["comparables"] == 0

    ok = [r for r in results if r["engine"] == "gemini-3-flash"]
    assert len(ok) == 3, ok
    assert all(r["error"] is None and r["aciertos"] == 8 for r in ok)


async def test_s6_7_el_error_persistido_no_expone_el_detalle_del_extractor(authapi: Api) -> None:
    """Un adaptador no confiable no puede escribir su excepción en BD ni en el contrato del lote."""
    from ocr.benchmark import run_benchmark

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, slug="bm-safe-error")
    secret = "respuesta externa no confiable con secreto"

    await run_benchmark(
        tenant_id,
        company_id,
        file_id,
        content=real_jpeg_bytes(),
        content_type="image/jpeg",
        truth=_truth(),
        own_cif=OWN_CIF,
        ocr_experiment_enabled=True,
        extractors=[("azure-docintel", make_extractor(error=RuntimeError(secret)))],
    )

    results = await fetch_benchmark_results(dsns, file_id=file_id)
    assert {row["error"] for row in results} == {"engine_failed"}
    assert all(secret not in str(row) for row in results)


async def test_s6_7_un_motor_que_agota_su_timeout_se_guarda_como_fallo_y_no_bloquea(
    authapi: Api, monkeypatch
) -> None:
    """C2: un proveedor que no responde termina con una etiqueta segura, no deja el job colgado."""
    import asyncio

    from ocr import benchmark

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, slug="bm-timeout")

    class SlowExtractor:
        async def extract(self, content: bytes, content_type: str):
            del content, content_type
            await asyncio.sleep(1)
            raise AssertionError("el timeout debía cancelar antes esta lectura")

    monkeypatch.setattr(benchmark, "_COMBINATION_TIMEOUT_SECONDS", 0.01)
    await benchmark.run_benchmark(
        tenant_id,
        company_id,
        file_id,
        content=real_jpeg_bytes(),
        content_type="image/jpeg",
        truth=_truth(),
        own_cif=OWN_CIF,
        ocr_experiment_enabled=True,
        extractors=[("slow", SlowExtractor())],
    )

    results = await fetch_benchmark_results(dsns, file_id=file_id)
    assert len(results) == 3
    assert {row["error"] for row in results} == {"engine_failed"}


async def test_s6_7_el_lote_recibe_un_fallo_de_orquestacion(authapi: Api, monkeypatch) -> None:
    """C13: un fallo fuera de una combinación concreta se propaga solo cuando el lote lo pide."""
    from ocr import benchmark

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, slug="bm-orchestration-failure")

    async def broken_variants(_pages: list[object]):
        raise RuntimeError("infraestructura rota")

    monkeypatch.setattr(benchmark, "_build_variants", broken_variants)
    with pytest.raises(RuntimeError, match="infraestructura rota"):
        await benchmark.run_benchmark(
            tenant_id,
            company_id,
            file_id,
            content=real_jpeg_bytes(),
            content_type="image/jpeg",
            truth=_truth(),
            own_cif=OWN_CIF,
            ocr_experiment_enabled=True,
            extractors=[("gemini-3-flash", make_extractor(_reading_invoice()))],
            raise_on_orchestration_error=True,
        )


async def test_s6_7_los_seis_motores_sin_credenciales_persisten_su_error(authapi: Api) -> None:
    """Una configuración parcial no puede esconder motores del denominador del benchmark."""
    from ocr.benchmark import run_benchmark
    from ocr.ranking_engines import build_named_ranking_extractors
    from shared.config import Settings

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, slug="bm-unavailable-engines")

    await run_benchmark(
        tenant_id,
        company_id,
        file_id,
        content=real_jpeg_bytes(),
        content_type="image/jpeg",
        truth=_truth(),
        own_cif=OWN_CIF,
        ocr_experiment_enabled=True,
        extractors=build_named_ranking_extractors(Settings(_env_file=None)),  # type: ignore[call-arg]
    )

    results = await fetch_benchmark_results(dsns, file_id=file_id)
    assert len(results) == 18
    assert {row["engine"] for row in results} == {
        "gemini-3-flash",
        "gemini-3-pro",
        "claude-vertex",
        "gpt-5.1",
        "azure-docintel",
        "mistral-ocr-4",
    }
    assert {row["error"] for row in results} == {"engine_failed"}


async def test_c4_reejecutar_el_benchmark_sobre_la_misma_factura_actualiza_no_duplica(
    authapi: Api,
) -> None:
    """spec: C4 -- ON CONFLICT (uploaded_file_id, variant, engine) DO UPDATE, nunca duplica."""
    from ocr.benchmark import run_benchmark

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, slug="bm-c4")
    content = real_jpeg_bytes()

    await run_benchmark(
        tenant_id,
        company_id,
        file_id,
        content=content,
        content_type="image/jpeg",
        truth=_truth(),
        own_cif=OWN_CIF,
        ocr_experiment_enabled=True,
        extractors=[("gemini-3-flash", make_extractor(_reading_invoice(total="999.00")))],
    )
    assert await count_benchmark_results(dsns, file_id=file_id) == 3

    # Segunda ejecución: la misma factura, con una lectura DISTINTA -> actualiza, no duplica.
    await run_benchmark(
        tenant_id,
        company_id,
        file_id,
        content=content,
        content_type="image/jpeg",
        truth=_truth(),
        own_cif=OWN_CIF,
        ocr_experiment_enabled=True,
        extractors=[("gemini-3-flash", make_extractor(_reading_invoice()))],
    )

    assert await count_benchmark_results(dsns, file_id=file_id) == 3
    results = await fetch_benchmark_results(dsns, file_id=file_id)
    assert all(r["aciertos"] == 8 for r in results), results  # refleja la 2ª lectura, no la 1ª


async def test_un_pdf_usa_el_mismo_buffer_en_las_3_variantes_sin_intentar_realzarlo(
    authapi: Api,
) -> None:
    """spec §2 -- un PDF no es "realzable"; las 3 variantes son el mismo buffer sin transformar,
    nunca un error por intentar aplicarle CLAHE/realce a un PDF."""
    from ocr.benchmark import run_benchmark

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, slug="bm-pdf")

    await run_benchmark(
        tenant_id,
        company_id,
        file_id,
        content=b"%PDF-1.4 contenido de prueba, no es una imagen real",
        content_type="application/pdf",
        truth=_truth(),
        own_cif=OWN_CIF,
        ocr_experiment_enabled=True,
        extractors=[("gemini-3-flash", make_extractor(_reading_invoice()))],
    )

    results = await fetch_benchmark_results(dsns, file_id=file_id)
    assert len(results) == 3, results
    assert all(r["error"] is None for r in results), results


async def test_c23_el_cif_y_nombre_de_contraparte_de_la_lectura_viajan_cifrados_en_reposo(
    authapi: Api,
) -> None:
    """spec: C23 -- la lectura del motor guarda el CIF/nombre de contraparte cifrados con la clave
    del tenant (ADR-0018), nunca en claro."""
    from ocr.benchmark import run_benchmark

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, slug="bm-c23")

    await run_benchmark(
        tenant_id,
        company_id,
        file_id,
        content=real_jpeg_bytes(),
        content_type="image/jpeg",
        truth=_truth(),
        own_cif=OWN_CIF,
        ocr_experiment_enabled=True,
        extractors=[("gemini-3-flash", make_extractor(_reading_invoice()))],
    )

    raw = await fetch_benchmark_results_raw(dsns, file_id=file_id)
    assert len(raw) == 3, raw
    for row in raw:
        # Ni el CIF ni el nombre en claro deben aparecer en los bytes crudos de la columna.
        assert row["counterparty_tax_id"] is not None
        raw_bytes = bytes(row["counterparty_tax_id"])
        assert COUNTERPARTY_CIF.encode() not in raw_bytes
        assert b"Proveedor SA" not in bytes(row["counterparty_name"])

    decrypted = await fetch_benchmark_results(dsns, file_id=file_id)
    assert all(r["counterparty_tax_id"] == COUNTERPARTY_CIF for r in decrypted)
    assert all(r["counterparty_name"] == "Proveedor SA" for r in decrypted)


async def test_c23_el_cif_y_nombre_de_contraparte_no_viajan_en_claro_dentro_del_reading_jsonb(
    authapi: Api,
) -> None:
    """spec: C23 -- refuerzo del test anterior (auditoría 2026-08-11, hallazgo CRÍTICO real): el CIF
    y el nombre de la contraparte NO deben aparecer en ningún punto del texto JSON de la columna
    `reading` (sin descifrar), ni siquiera aunque las columnas `bytea` dedicadas ya los cifren --
    viajar también en claro dentro del JSONB habría anulado el propósito de C23 por duplicado."""
    from ocr.benchmark import run_benchmark

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, slug="bm-c23b")

    await run_benchmark(
        tenant_id,
        company_id,
        file_id,
        content=real_jpeg_bytes(),
        content_type="image/jpeg",
        truth=_truth(),
        own_cif=OWN_CIF,
        ocr_experiment_enabled=True,
        extractors=[("gemini-3-flash", make_extractor(_reading_invoice()))],
    )

    raw = await fetch_benchmark_results_raw(dsns, file_id=file_id)
    assert len(raw) == 3, raw
    for row in raw:
        reading_text = row["reading"]
        assert isinstance(reading_text, str) and reading_text, row  # texto JSON crudo, no None
        assert COUNTERPARTY_CIF not in reading_text, reading_text
        assert "Proveedor SA" not in reading_text, reading_text
