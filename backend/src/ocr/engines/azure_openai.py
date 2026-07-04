"""Motor de lectura OCR basado en Azure OpenAI (gpt-5.1) vía chat-visión.

Candidato del bench de Fase 1. Como Gemini, no es una API OCR nativa: es un modelo multimodal al
que se le manda la imagen con un prompt que le pide transcribir la factura a markdown, fielmente y
sin inventar (regla anti-alucinación). Reusa la lógica de conexión del adaptador previo (rama
`feature/1.2-engine-azure-openai`): URL REST del despliegue, cabecera `api-key`, y config desde el
`.env`. Portado a la interfaz async `OcrEngine` y a salida markdown (no JSON estructurado).

Notas de despliegue:
- Residencia (plan §3 + ADR-0007): el despliegue debe ser **Data Zone Standard / EU**, nunca Global.
- gpt-5.1 es un modelo de razonamiento: usa `max_completion_tokens` (no `max_tokens`) y no admite
  `temperature` distinta de la de por defecto, así que no se envía.
- Visión por chat/completions acepta imágenes (JPEG/PNG/WebP), no PDF. El PDF se rasterizará en un
  paso previo común a los motores solo-imagen (issue #16); de momento se rechaza con error tipado.

SDK: REST directo con `httpx.AsyncClient`. Endpoint, clave y despliegue son secretos (en el `.env`).
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from ocr.engines.base import OcrEngine, OcrError, OcrPage, OcrResult

__all__ = ["AzureOpenAIEngine", "AzureOpenAIError", "OCR_PROMPT"]

# Mismo espíritu que el prompt de Gemini: transcripción fiel, sin inventar. Se mantiene una copia
# local para no acoplar este motor al de Gemini (que arrastra el SDK de Google al importarse).
OCR_PROMPT = (
    "Eres un OCR de facturas. Transcribe TODO el contenido del documento a Markdown, "
    "respetando tablas, importes, fechas e identificadores fiscales tal como aparecen. "
    "No inventes ni completes datos: si algo es ilegible, déjalo en blanco. "
    "Devuelve solo el Markdown, sin comentarios ni explicaciones."
)

_DEFAULT_TIMEOUT_S = 90.0
_MAX_OUTPUT_TOKENS = 4000

# Visión de gpt acepta imágenes, no PDF (ver nota de cabecera).
_IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class AzureOpenAIError(OcrError):
    """Fallo del motor Azure OpenAI: credenciales, tipo no soportado o error de la API."""


class AzureOpenAIEngine(OcrEngine):
    """Adaptador de Azure OpenAI (gpt-5.1) a la interfaz común `OcrEngine`."""

    def __init__(
        self,
        endpoint: str | None,
        key: str | None,
        deployment: str | None,
        *,
        name: str = "azure-openai",
        api_version: str = "2024-12-01-preview",
        prompt: str = OCR_PROMPT,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        client: Any | None = None,
    ) -> None:
        """Crea el motor. `client` (httpx.AsyncClient o doble) permite testear sin red ni coste."""
        if client is None and (not endpoint or not key or not deployment):
            raise AzureOpenAIError(
                "Azure OpenAI sin configurar: faltan "
                "AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_KEY / AZURE_OPENAI_DEPLOYMENT en el .env"
            )
        self._endpoint = endpoint
        self._key = key
        self._deployment = deployment
        self._name = name
        self._api_version = api_version
        self._prompt = prompt
        self._timeout_s = timeout_s
        self._client = client

    @property
    def name(self) -> str:
        return self._name

    async def extract(self, file_path: str | Path) -> OcrResult:
        """Manda la factura a gpt-visión y devuelve el markdown transcrito, normalizado."""
        path = Path(file_path)
        if not path.is_file():
            raise AzureOpenAIError(f"No existe el fichero a procesar: {path}")

        payload = {
            "messages": self._build_messages(path),
            "max_completion_tokens": _MAX_OUTPUT_TOKENS,
        }
        headers = {"api-key": self._key or "", "Content-Type": "application/json"}
        url = self._chat_completions_url()

        try:
            if self._client is not None:  # cliente inyectado en test
                response = await self._client.post(url, headers=headers, json=payload)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                    response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
        except AzureOpenAIError:
            raise
        except Exception as exc:  # frontera del proveedor: nada crudo cruza hacia el llamador
            raise AzureOpenAIError(f"Azure OpenAI falló al procesar {path.name}: {exc}") from exc

        return self._parse(body)

    def _chat_completions_url(self) -> str:
        """URL REST del despliegue (el nombre del despliegue va en la ruta, no el modelo)."""
        base = (self._endpoint or "").rstrip("/")
        return (
            f"{base}/openai/deployments/{self._deployment}"
            f"/chat/completions?api-version={self._api_version}"
        )

    def _build_messages(self, path: Path) -> list[dict[str, Any]]:
        """Mensaje de chat-visión: el prompt de transcripción + la imagen como data URI."""
        mime = _IMAGE_MIME.get(path.suffix.lower())
        if mime is None:
            raise AzureOpenAIError(
                f"Tipo de fichero no soportado por gpt-visión: {path.suffix or '(sin extensión)'} "
                "(el PDF se rasterizará en un paso previo, issue #16)"
            )
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": self._prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                ],
            }
        ]

    def _parse(self, body: dict[str, Any]) -> OcrResult:
        """Normaliza la respuesta de chat/completions a `OcrResult` (una sola página)."""
        choices = body.get("choices") or []
        markdown = ""
        if choices:
            markdown = (choices[0].get("message") or {}).get("content") or ""
        usage = body.get("usage") or None
        return OcrResult(
            engine=self.name,
            model=body.get("model") or self._deployment or self._name,
            pages=(OcrPage(index=0, markdown=markdown),),
            usage=usage,
            raw={"model": body.get("model"), "usage": usage},
        )
