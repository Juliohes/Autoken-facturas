"""Motor del bench: Azure OpenAI (gpt-4.1 / gpt-4o) vía chat-visión.

Llama al endpoint REST de *chat completions* del despliegue de Azure OpenAI con la factura como
imagen y un prompt que fuerza salida JSON (`response_format=json_object`, `temperature=0`).
Mide la latencia real y calcula el coste a partir del ``usage`` que devuelve el servicio y de la
tarifa configurada (EUR por 1.000 tokens). Cumple la regla anti-alucinación delegando el parseo
en :func:`ocr.bench.engines.base.parse_invoice_json` (campos no legibles → ``null`` → ``None``).

Requisito de residencia (plan §3 + ADR-0007): el despliegue debe ser **Data Zone Standard / EU**,
nunca Global. Esto se decide al crear el despliegue en Azure; el adaptador solo usa su nombre.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import httpx

from ocr.bench.engines.base import (
    EngineError,
    build_extraction_messages,
    encode_image,
    parse_invoice_json,
)
from ocr.bench.schema import EngineResult, InvoiceFields
from shared.config import Settings, get_settings

ENGINE_NAME = "azure-openai"
_DEFAULT_TIMEOUT_S = 90.0
_MAX_OUTPUT_TOKENS = 1500


@dataclass(frozen=True)
class AzureOpenAIConfig:
    """Parámetros de conexión y tarifa del despliegue de Azure OpenAI."""

    endpoint: str
    api_key: str
    deployment: str
    api_version: str = "2024-10-21"
    eur_per_1k_input: Decimal = Decimal(0)
    eur_per_1k_output: Decimal = Decimal(0)

    @property
    def is_configured(self) -> bool:
        """True si hay endpoint, clave y despliegue para poder llamar al servicio."""
        return bool(self.endpoint and self.api_key and self.deployment)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> AzureOpenAIConfig:
        """Construye la config desde las variables de entorno (`.env`)."""
        s = settings or get_settings()
        return cls(
            endpoint=s.azure_openai_endpoint,
            api_key=s.azure_openai_key,
            deployment=s.azure_openai_deployment,
            api_version=s.azure_openai_api_version,
            eur_per_1k_input=s.azure_openai_eur_per_1k_input,
            eur_per_1k_output=s.azure_openai_eur_per_1k_output,
        )

    def chat_completions_url(self) -> str:
        """URL REST del despliegue (el nombre del despliegue va en la ruta, no el modelo)."""
        base = self.endpoint.rstrip("/")
        return (
            f"{base}/openai/deployments/{self.deployment}"
            f"/chat/completions?api-version={self.api_version}"
        )


class AzureOpenAIEngine:
    """Adaptador de Azure OpenAI conforme al protocolo `OcrEngine`.

    El cliente HTTP se inyecta para poder testear sin red ni coste (httpx.MockTransport).
    """

    name = ENGINE_NAME

    def __init__(self, config: AzureOpenAIConfig, *, client: httpx.Client | None = None) -> None:
        if not config.is_configured:
            raise EngineError(
                "Azure OpenAI sin configurar: faltan AZURE_OPENAI_ENDPOINT/KEY/DEPLOYMENT en .env"
            )
        self._config = config
        self._client = client or httpx.Client(timeout=_DEFAULT_TIMEOUT_S)
        self._owns_client = client is None

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> AzureOpenAIEngine:
        return cls(AzureOpenAIConfig.from_settings(settings))

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    @staticmethod
    def _as_int(value: object) -> int:
        return value if isinstance(value, int) else 0

    def _cost_eur(self, usage: dict[str, object]) -> Decimal:
        prompt_tokens = self._as_int(usage.get("prompt_tokens"))
        completion_tokens = self._as_int(usage.get("completion_tokens"))
        return (
            Decimal(prompt_tokens) * self._config.eur_per_1k_input
            + Decimal(completion_tokens) * self._config.eur_per_1k_output
        ) / Decimal(1000)

    def extract(self, image_path: Path) -> EngineResult:
        """Extrae los campos de la factura. No lanza por fallos del servicio: los envuelve."""
        started = time.perf_counter()
        try:
            image_b64, mime = encode_image(image_path)
            payload = {
                "messages": build_extraction_messages(image_b64, mime),
                "temperature": 0,
                "max_tokens": _MAX_OUTPUT_TOKENS,
                "response_format": {"type": "json_object"},
            }
            response = self._client.post(
                self._config.chat_completions_url(),
                headers={"api-key": self._config.api_key, "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            usage = body.get("usage", {}) or {}
            fields = parse_invoice_json(content)
            cost = self._cost_eur(usage)
            raw = {"usage": usage}
        except (httpx.HTTPError, EngineError, KeyError, IndexError, ValueError) as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return EngineResult(
                engine=self.name,
                fields=InvoiceFields(),
                duration_ms=duration_ms,
                error=f"{type(exc).__name__}: {exc}",
            )

        duration_ms = int((time.perf_counter() - started) * 1000)
        return EngineResult(
            engine=self.name,
            fields=fields,
            duration_ms=duration_ms,
            cost_eur=cost,
            raw=raw,
        )
