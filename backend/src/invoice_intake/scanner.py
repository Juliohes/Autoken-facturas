"""Antivirus del intake (fail-closed, ADR-0015): ningún fichero se persiste sin escanear limpio.

Función de módulo `scan(content)` que el servicio invoca antes de almacenar (spec S2.1 C6/C7):
- limpio -> retorna `None`;
- infectado -> `ScanInfected` (el llamante responde 422);
- antivirus no disponible -> `ScannerUnavailable` (el llamante responde 503; **fail-closed**: sin
  ClamAV no entra ningún fichero).

Dos backends tras la misma interfaz:
- `SignatureScanner`: en proceso, sin red; detecta la cadena de prueba estándar **EICAR**. Es el
  backend de desarrollo/CI (los tests inyectan un JPEG con EICAR embebido y debe rechazarse).
- `ClamdScanner`: ClamAV real vía el daemon `clamd` (producción). Si el daemon no responde ->
  `ScannerUnavailable` (fail-closed), nunca "limpio por defecto".

Selección: `settings.virus_scanner_backend` la fuerza; sin fijar, `signature` fuera de producción y
`clamd` en producción. `scan` es una función de módulo a propósito, para que los tests puedan
inyectar el "daemon caído" con `monkeypatch.setattr(scanner, "scan", ...)` (C7).
"""

from __future__ import annotations

import io
from functools import lru_cache
from typing import Protocol

import clamd

from shared.config import get_settings

# Firma de la cadena de prueba EICAR (inofensiva; todos los AV la detectan). El scanner de firma la
# busca en los bytes: basta el fragmento identificador, no la cadena completa.
_EICAR_SIGNATURE = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"


class ScannerError(Exception):
    """Raíz de los errores del antivirus del intake."""


class ScanInfected(ScannerError):
    """El antivirus marcó el contenido como infectado (-> 422). El fichero no se persiste."""


class ScannerUnavailable(ScannerError):
    """El antivirus no está disponible (-> 503). Fail-closed: no entra nada sin escanear."""


class VirusScanner(Protocol):
    """Interfaz común de los backends de antivirus."""

    def scan(self, content: bytes) -> None:
        """Escanea `content`; lanza `ScanInfected`/`ScannerUnavailable`, o `None` si limpio."""
        ...


class SignatureScanner:
    """Backend en proceso (dev/CI): detecta la firma EICAR sin depender de red ni de un daemon."""

    def scan(self, content: bytes) -> None:
        if _EICAR_SIGNATURE in content:
            raise ScanInfected("Firma EICAR detectada por el scanner de firma")


class ClamdScanner:
    """Backend real (producción): delega en el daemon ClamAV vía `clamd` (fail-closed)."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port

    def scan(self, content: bytes) -> None:
        client = clamd.ClamdNetworkSocket(host=self._host, port=self._port)
        try:
            result = client.instream(io.BytesIO(content))
        except (clamd.ConnectionError, OSError) as exc:  # daemon caído / no desplegado
            raise ScannerUnavailable("ClamAV no responde") from exc
        status, signature = result["stream"]
        if status == "FOUND":
            raise ScanInfected(f"ClamAV detectó una amenaza: {signature}")


@lru_cache(maxsize=4)
def _scanner_for(backend: str, host: str, port: int) -> VirusScanner:
    """Backend de antivirus memoizado por configuración (issue #67): se reutiliza entre peticiones.

    `SignatureScanner` no tiene estado; `ClamdScanner` guarda host/port y abre el socket en cada
    scan, así que reutilizar la instancia no comparte conexiones. Un backend desconocido es error de
    configuración (fail-loud), no un fallback silencioso.
    """
    if backend == "signature":
        return SignatureScanner()
    if backend == "clamd":
        return ClamdScanner(host, port)
    raise ScannerUnavailable(f"Backend de antivirus desconocido: {backend!r}")


def _select_scanner() -> VirusScanner:
    """Elige el backend según la configuración: `virus_scanner_backend` lo fuerza; sin fijar,
    `signature` fuera de producción y `clamd` en producción."""
    settings = get_settings()
    backend = settings.virus_scanner_backend
    if backend is None:
        backend = "clamd" if settings.is_production else "signature"
    return _scanner_for(backend, settings.clamav_host, settings.clamav_port)


def scan(content: bytes) -> None:
    """Escanea `content` con el backend configurado. Función de módulo (inyectable en test)."""
    _select_scanner().scan(content)
