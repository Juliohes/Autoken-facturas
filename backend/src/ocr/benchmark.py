"""Motor de ejecución real del benchmark de variante x motor (S6.7, spec
docs/specs/S6.7-benchmark-real-motor-variante.md, Área A/B, C1-C9/C23).

A diferencia de `ocr.comparison`/`ocr.benchmark_scoring` (módulos PUROS de puntuación, sin ningún
I/O), `run_benchmark` es un módulo de ORQUESTACIÓN (Postgres, cifrado por tenant) que vive en el
paquete `ocr` por decisión explícita de esta tarea -- a diferencia de `jobs.ocr_ranking` (S4.8), que
vive en `jobs`.

`own_cif`/`ocr_experiment_enabled` llegan YA resueltos como parámetros (2026-08-11, S6.7 auditoría,
hallazgo de arquitectura): antes este módulo importaba `companies.repository`/
`platform_admin.settings_repository` para resolverlos él mismo, invirtiendo la dirección de
dependencias del monorepo (ningún otro módulo de `ocr` depende de esos contextos). Mismo patrón ya
auditado que `jobs.ocr_ranking.run_ocr_ranking` (S4.8): el llamador (`jobs.ocr_benchmark.
run_ocr_benchmark_task`) resuelve ambos valores en su propia sesión corta, `ocr.benchmark` solo los
usa.

`extractors` es OBLIGATORIO, como pares `(engine_name, InvoiceExtractor)`: así se conoce el nombre
del motor AUNQUE `.extract()` falle antes de devolver ningún `ExtractedInvoice.engine` (C2, a
diferencia de `run_ocr_ranking`, que solo loguea y descarta un motor caído sin persistir nada para
él). Ningún fallback interno a motores reales -- el único punto de producción legítimo que construye
motores reales desde `.env` es `jobs.ocr_benchmark.run_ocr_benchmark_task` (mismo criterio ya
auditado que `run_ocr_ranking`/`run_ocr`; ver sus docstrings para el incidente real de coste de S4.8
que este patrón evita). Llamar a `run_benchmark` directamente (como hace la mayoría de los tests) no
puede disparar llamadas de pago reales por omisión.

3 variantes (`original`/`enhanced`/`clahe`) x N motores por combinación: EN SECUENCIA entre
variantes, EN PARALELO dentro de cada variante (C3) -- el pico de llamadas simultáneas nunca supera
el número de motores. Un fallo de un motor en una variante concreta se persiste como una fila de
error (C2), nunca aborta el resto. Un fallo al GENERAR la propia variante (enhance/clahe sobre una
imagen corrupta) tampoco aborta el benchmark completo: se trata como si esa variante hubiera fallado
para TODOS sus motores -- se persiste una fila de error por motor, sin llamar a ningún proveedor con
una imagen que no llegó a generarse (decisión de diseño propia, sin test explícito de la spec, spec
§5: "usa tu criterio, documenta la decisión" -- coherente con el resto del módulo, nunca se arriesga
una llamada de pago sobre un insumo que se sabe roto).

`_redact_reading_for_storage` retira `counterparty_tax_id`/`counterparty_name` del JSONB `reading`
justo antes de persistir, DESPUÉS de puntuar (2026-08-11, S6.7 auditoría, hallazgo CRÍTICO de
seguridad): esos dos campos ya viajan cifrados en sus columnas `bytea` dedicadas (C23,
`ocr.benchmark_repository`); dejarlos también dentro de `reading` los habría hecho viajar en claro
por partida doble, anulando el propósito de C23 -- el mismo tipo de fallo ya corregido el 09/08/2026
en el endpoint "Ver ejemplos" del Ranking OCR.

`_run_variant` abre su propia `tenant_session` SOLO para persistir, DESPUÉS de que el `gather` de
esa variante ya haya resuelto sus resultados (2026-08-11, S6.7 auditoría, hallazgo de patrones):
mantener una transacción de Postgres abierta durante las llamadas reales a los motores (red,
minutos) competía por el pool de conexiones con el OCR de producción en cada factura confirmada --
mismo tipo de agotamiento de pool que causó el incidente real ya documentado y corregido en S5.5.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog

from ocr.analysis import InvoiceAnalysis, analyze_invoice
from ocr.benchmark_repository import upsert_benchmark_result
from ocr.benchmark_scoring import score_combination
from ocr.extraction import ExtractedInvoice, InvoiceExtractor
from ocr.preprocess.clahe import CLAHE_CONTENT_TYPE, clahe_invoice_image
from ocr.preprocess.enhance import (
    ENHANCED_CONTENT_TYPE,
    SUPPORTED_CONTENT_TYPES,
    enhance_invoice_image,
)
from ocr.scoring import serialize_reading
from shared.config import get_settings
from shared.db import tenant_session
from shared.encryption import tenant_encryption_key

logger = structlog.get_logger(__name__)

__all__ = ["run_benchmark"]

# Ningún proveedor puede consumir indefinidamente un worker ni provocar que ARQ reentregue el lote
# por superar su límite global. El timeout se aplica por combinación y el resultado queda guardado
# como `engine_failed`, igual que cualquier caída externa (C2).
_COMBINATION_TIMEOUT_SECONDS = 120

# Nombres de variante (spec §2) -- procesadas en este orden fijo, una detrás de otra (C3).
_VARIANT_ORIGINAL = "original"
_VARIANT_ENHANCED = "enhanced"
_VARIANT_CLAHE = "clahe"


@dataclass(frozen=True)
class _Variant:
    """Una variante de imagen ya generada -- `content`/`content_type` a `None` cuando su generación
    falló (`error` relleno): ninguna combinación de esa variante llega a llamar a ningún motor."""

    name: str
    content: bytes | None
    content_type: str | None
    error: str | None


@dataclass(frozen=True)
class _CombinationResult:
    """Fila a persistir para una combinación (variante ya fijada, motor) -- `error` relleno excluye
    al resto de campos (motor caído, C2); con éxito, `error` es `None` y el resto viene relleno."""

    model: str | None
    counterparty_tax_id: str | None
    counterparty_name: str | None
    reading: dict[str, Any] | None
    field_results: list[dict[str, Any]]
    tax_lines_matched: bool | None
    aciertos: int
    comparables: int
    error: str | None
    duration_ms: int | None


async def run_benchmark(
    tenant_id: UUID,
    company_id: UUID,
    uploaded_file_id: UUID,
    *,
    content: bytes,
    content_type: str,
    truth: Mapping[str, object],
    own_cif: str,
    ocr_experiment_enabled: bool,
    extractors: list[tuple[str, InvoiceExtractor]],
    raise_on_orchestration_error: bool = False,
) -> None:
    """Ejecuta las combinaciones (variante, motor) sobre una factura y persiste cada resultado.

    Guarda de entrada (mismo criterio que `run_ocr_ranking`): interruptor apagado o sin motores ->
    no hace nada, coste cero, sin abrir ninguna sesión de Postgres (C1 del interruptor, spec §4).
    `raise_on_orchestration_error` solo lo usa el lote retroactivo: necesita contar como fallida una
    factura cuando falla la orquestación (almacén/persistencia). Los fallos de motor y de generar
    una variante siguen aislados en sus propias filas de resultado en ambos modos.
    """
    if not ocr_experiment_enabled or not extractors:
        return
    try:
        for variant in await _build_variants(content, content_type):
            await _run_variant(
                tenant_id,
                company_id=company_id,
                uploaded_file_id=uploaded_file_id,
                variant=variant,
                own_cif=own_cif,
                truth=truth,
                extractors=extractors,
            )
    except Exception:  # noqa: BLE001  (solo el lote necesita distinguir fallo de orquestación)
        logger.error("benchmark.failed", uploaded_file_id=str(uploaded_file_id))
        if raise_on_orchestration_error:
            raise


async def _build_variants(content: bytes, content_type: str) -> list[_Variant]:
    """Genera las 3 variantes de imagen. Formato no fotografiable (p. ej. PDF, spec §2): las 3 son
    el mismo buffer, sin transformar -- ni `enhanced` ni `clahe` se intentan sobre un PDF. Foto:
    `original` siempre disponible; `enhanced`/`clahe` se generan a partir del ORIGINAL (nunca uno a
    partir del otro, spec §5.1) -- un fallo al generarlas se aísla (ver docstring del módulo)."""
    if content_type not in SUPPORTED_CONTENT_TYPES:
        return [
            _Variant(_VARIANT_ORIGINAL, content, content_type, None),
            _Variant(_VARIANT_ENHANCED, content, content_type, None),
            _Variant(_VARIANT_CLAHE, content, content_type, None),
        ]

    variants = [_Variant(_VARIANT_ORIGINAL, content, content_type, None)]
    for name, builder, result_content_type in (
        (_VARIANT_ENHANCED, enhance_invoice_image, ENHANCED_CONTENT_TYPE),
        (_VARIANT_CLAHE, clahe_invoice_image, CLAHE_CONTENT_TYPE),
    ):
        try:
            # Coste real de CPU (decodificar + realce/CLAHE + codificar): fuera del event loop,
            # mismo criterio que `jobs.ocr`/`jobs.ocr.run_ocr_comparison`.
            generated = await asyncio.to_thread(builder, content, content_type)
            variants.append(_Variant(name, generated, result_content_type, None))
        except Exception:  # noqa: BLE001  (preprocesado: se aísla, no aborta el benchmark)
            logger.error("benchmark.variant_generation_failed", variant=name)
            variants.append(_Variant(name, None, None, "variant_generation_failed"))
    return variants


async def _run_variant(
    tenant_id: UUID,
    *,
    company_id: UUID,
    uploaded_file_id: UUID,
    variant: _Variant,
    own_cif: str,
    truth: Mapping[str, object],
    extractors: list[tuple[str, InvoiceExtractor]],
) -> None:
    """Calcula los resultados de esta variante (llamando a los motores reales SIN ninguna sesión de
    Postgres abierta) y los persiste al final, en una sesión corta abierta solo para eso -- ver
    docstring del módulo para el motivo (auditoría, hallazgo de patrones: agotamiento del pool de
    conexiones)."""
    if variant.content is None or variant.content_type is None:
        # La variante no llegó a generarse: fila de error por motor, sin llamar a ningún proveedor
        # (C2, generalizado a un fallo de preprocesado) -- no hace falta ningún `gather`.
        results: list[tuple[str, _CombinationResult]] = [
            (
                engine_name,
                _CombinationResult(
                    model=None,
                    counterparty_tax_id=None,
                    counterparty_name=None,
                    reading=None,
                    field_results=[],
                    tax_lines_matched=None,
                    aciertos=0,
                    comparables=0,
                    error=variant.error,
                    duration_ms=None,
                ),
            )
            for engine_name, _ in extractors
        ]
    else:
        content, content_type = variant.content, variant.content_type
        gathered = await asyncio.gather(
            *(
                _run_combination(engine_name, extractor, content, content_type, own_cif, truth)
                for engine_name, extractor in extractors
            )
        )
        results = list(zip((engine_name for engine_name, _ in extractors), gathered, strict=True))

    async with tenant_session(tenant_id, company_id) as session:
        encryption_key = _encryption_key_for(tenant_id)
        for engine_name, result in results:
            await upsert_benchmark_result(
                session,
                company_id=company_id,
                uploaded_file_id=uploaded_file_id,
                variant=variant.name,
                engine=engine_name,
                model=result.model,
                counterparty_tax_id=result.counterparty_tax_id,
                counterparty_name=result.counterparty_name,
                reading=result.reading,
                field_results=result.field_results,
                tax_lines_matched=result.tax_lines_matched,
                aciertos=result.aciertos,
                comparables=result.comparables,
                error=result.error,
                duration_ms=result.duration_ms,
                encryption_key=encryption_key,
            )


def _encryption_key_for(tenant_id: UUID) -> str:
    return tenant_encryption_key(get_settings(), tenant_id)


async def _run_combination(
    engine_name: str,
    extractor: InvoiceExtractor,
    content: bytes,
    content_type: str,
    own_cif: str,
    truth: Mapping[str, object],
) -> _CombinationResult:
    """Ejecuta un único (variante ya fijada, motor) -- nunca lanza (C2): un fallo real del proveedor
    se traduce en `error` relleno + `aciertos`/`comparables` a 0, nunca en una excepción."""
    started = time.monotonic()
    try:
        extracted = await asyncio.wait_for(
            extractor.extract(content, content_type), timeout=_COMBINATION_TIMEOUT_SECONDS
        )
        duration_ms = _elapsed_ms(started)
        analysis = analyze_invoice(extracted, own_cif)
        reading = _build_reading(extracted, analysis)
        # La puntuación SÍ necesita el CIF/nombre de contraparte de `reading` (score_combination
        # compara esos dos campos igual que el resto); se retiran DESPUÉS de puntuar, solo de lo
        # que se persiste (ver `_redact_reading_for_storage`) -- si se retiraran antes,
        # `score_combination` los vería siempre ausentes y ambos campos fallarían por omisión (bug
        # real detectado al implementar el hallazgo CRÍTICO de la auditoría, corregido en el mismo
        # cambio).
        score = score_combination(reading, truth)
        return _CombinationResult(
            model=extracted.model,
            counterparty_tax_id=analysis.counterparty_tax_id,
            counterparty_name=analysis.counterparty_name,
            reading=_redact_reading_for_storage(reading),
            field_results=[
                {"field": field_score.field, "match": field_score.match}
                for field_score in score.field_scores
            ],
            tax_lines_matched=score.tax_lines_matched,
            aciertos=score.aciertos,
            comparables=score.comparables,
            error=None,
            duration_ms=duration_ms,
        )
    except Exception:  # noqa: BLE001  (motor caído: se persiste el error, nunca se propaga)
        # Un extractor es un adaptador externo: su excepción puede incluir prompts, respuestas o
        # credenciales. El contrato persistible es deliberadamente un código estable y seguro.
        logger.error("benchmark.engine_failed", engine=engine_name)
        return _CombinationResult(
            model=None,
            counterparty_tax_id=None,
            counterparty_name=None,
            reading=None,
            field_results=[],
            tax_lines_matched=None,
            aciertos=0,
            comparables=0,
            error="engine_failed",
            duration_ms=_elapsed_ms(started),
        )


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _build_reading(extracted: ExtractedInvoice, analysis: InvoiceAnalysis) -> dict[str, Any]:
    """`ocr.scoring.serialize_reading` reutilizado (no se reinventa el shape), con los tramos de IVA
    normalizados a la clave `iva_pct` (en vez de `rate`).

    Hallazgo real durante la implementación (sin test explícito en la spec): `serialize_tax_lines`/
    `serialize_reading` usan `rate` -- el vocabulario de `ExtractedTaxLine`, pensado para el prompt
    del extractor (`ocr.extraction_json`) -- mientras que TODO el resto del dominio
    (`invoice_tax_lines`, `ConfirmTaxLine`, `ocr.benchmark_scoring`, y la propia `truth` que recibe
    `run_benchmark`) usa `iva_pct`. Sin esta normalización, `ocr.benchmark_scoring._score_tax_lines`
    nunca encontraría el tipo de IVA del lado de la lectura (`line.get("iva_pct")` siempre `None`) y
    ningún tramo puntuaría jamás, pase lo que pase con `base`/`cuota`. Se normaliza aquí, en el
    límite de este módulo, en vez de tocar `ocr.scoring` (que sigue sirviendo a `ocr.comparison`/
    `jobs.ocr_ranking` con su formato ya establecido, sin cambio de comportamiento para ellos).

    Este dict SÍ lleva `counterparty_tax_id`/`counterparty_name` en claro (tal cual los pone
    `serialize_reading`): `score_combination` los necesita para puntuar esos dos campos igual que el
    resto -- se retiran justo antes de persistir, no aquí (ver `_redact_reading_for_storage`).
    """
    reading = serialize_reading(extracted, analysis)
    reading["tax_lines"] = [
        {"iva_pct": line.get("rate"), "base": line.get("base"), "cuota": line.get("cuota")}
        for line in reading.get("tax_lines", [])
    ]
    return reading


def _redact_reading_for_storage(reading: dict[str, Any]) -> dict[str, Any]:
    """Copia de `reading` SIN `counterparty_tax_id`/`counterparty_name` -- la única versión que se
    persiste en el JSONB `reading` (C23; hallazgo CRÍTICO real de seguridad, auditoría S6.7,
    2026-08-11).

    Esos dos campos ya viajan cifrados en sus columnas `bytea` dedicadas
    (`_CombinationResult.counterparty_tax_id`/`counterparty_name`, ver `_run_combination`); dejarlos
    también dentro de `reading` los habría hecho viajar en claro por partida doble, anulando el
    propósito de C23 -- el mismo tipo de fallo ya corregido el 09/08/2026 en el endpoint "Ver
    ejemplos" del Ranking OCR. Se aplica DESPUÉS de puntuar (`score_combination` sí necesita ver
    esos campos, ver `_build_reading`), nunca antes."""
    redacted = dict(reading)
    redacted.pop("counterparty_tax_id", None)
    redacted.pop("counterparty_name", None)
    return redacted
