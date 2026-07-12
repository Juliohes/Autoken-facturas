"""Resolver AEAT censal (L3, fuente autoritativa del par CIF+nombre).

Adaptador del servicio público de la AEAT "Comprobación de un NIF de un tercero a efectos censales"
(VNifV2, SOAP sobre mutual-TLS con certificado electrónico). Es la fuente **autoritativa**: su
"no identificado" es determinante (`negative_authoritative=True`) y compara el par CIF+nombre en el
propio censo, devolviendo la razón social oficial cuando el nombre no concuerda.

En CI va doblado (sin red ni certificado). La llamada real solo se ejerce en staging, con el
certificado de Julio montado como fichero (`settings.aeat_cert_path`/`aeat_cert_password`, en
`secrets/`, gitignored). El endpoint (preproducción vs producción) se confirma al validar en stg.
"""

from __future__ import annotations

import ssl
from typing import Any

from shared.config import Settings

from .base import ResolutionResult, ResolverUnavailable, run_blocking

# Valores del campo `Resultado` de VNifV2 relevantes para el veredicto. La AEAT responde, por cada
# contribuyente consultado, uno de estos literales; el mapeo a existencia (y, vía el nombre oficial
# devuelto, a coincidencia de nombre que calcula el servicio) es:
#   - IDENTIFICADO             -> el CIF consta (exists=True); AEAT devuelve la razón social oficial
#   - NIF/NOMBRE NO CONCUERDAN -> el CIF consta (exists=True) y AEAT devuelve el nombre oficial
#   - NO IDENTIFICADO          -> el CIF no consta en el censo (exists=False)
_RESULT_IDENTIFIED = "IDENTIFICADO"
_RESULT_NAME_MISMATCH = "NO IDENTIFICADO. NIF/NOMBRE NO COINCIDEN"
_RESULT_NAME_MISMATCH_ALT = "NIF/NOMBRE NO CONCUERDAN"
_RESULT_NOT_IDENTIFIED = "NO IDENTIFICADO"


class AeatCensalResolver:
    """Fuente AEAT censal (VNifV2) tras la interfaz `CifResolver`.

    El cliente SOAP (zeep sobre requests) es bloqueante: la llamada corre en un hilo vía
    `run_blocking`, que además traduce cualquier fallo a `ResolverUnavailable` con log. El cliente
    se construye una sola vez de forma perezosa (`_get_client`) y se reutiliza (no reparsea el WSDL
    en cada resolución). La AEAT caída lleva la verificación a `unverified`, nunca a "no existe".
    """

    source = "aeat"
    negative_authoritative = True

    def __init__(self, settings: Settings) -> None:
        if not settings.aeat_endpoint or not settings.aeat_cert_path:
            raise ResolverUnavailable(
                "AEAT censal no configurado (falta aeat_endpoint o aeat_cert_path)"
            )
        self._endpoint = settings.aeat_endpoint
        self._cert_path = settings.aeat_cert_path
        self._cert_password = settings.aeat_cert_password
        self._timeout = settings.aeat_timeout
        self._client: Any = None  # cliente zeep perezoso (se construye una vez, se reutiliza)

    def _ssl_context(self) -> ssl.SSLContext:
        """SSLContext con el certificado cliente (PEM cert+clave) para el mutual-TLS de la AEAT."""
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.load_cert_chain(certfile=self._cert_path, password=self._cert_password)
        return context

    def _build_client(self) -> Any:
        """Construye el cliente SOAP (bloqueante: monta el cert y parsea el WSDL). Solo staging."""
        # Import perezoso: zeep/requests solo se cargan cuando hay una resolución real (staging), no
        # en el arranque ni en los tests, que doblan el resolver.
        import requests
        from requests.adapters import HTTPAdapter
        from zeep import Client
        from zeep import Settings as ZeepSettings
        from zeep.transports import Transport

        class _ClientCertAdapter(HTTPAdapter):  # type: ignore[misc]  # HTTPAdapter es Any sin stubs
            def __init__(self, context: ssl.SSLContext) -> None:
                self._context = context
                super().__init__()

            def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
                kwargs["ssl_context"] = self._context
                super().init_poolmanager(*args, **kwargs)

        session = requests.Session()
        session.mount("https://", _ClientCertAdapter(self._ssl_context()))
        transport = Transport(
            session=session, timeout=self._timeout, operation_timeout=self._timeout
        )
        # XXE explícito (belt-and-suspenders): sin DTD, sin entidades, sin recursos externos, sin
        # depender del default de la librería al parsear la respuesta SOAP.
        zeep_settings = ZeepSettings(forbid_dtd=True, forbid_entities=True, forbid_external=True)
        return Client(self._endpoint, transport=transport, settings=zeep_settings)

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _resolve_sync(self, cif: str, name_read: str | None) -> ResolutionResult:
        client = self._get_client()
        response = client.service.VNifV2([{"Nif": cif, "Nombre": name_read or ""}])
        contribuyente = response[0] if isinstance(response, list) else response
        resultado = str(getattr(contribuyente, "Resultado", "")).strip().upper()
        official_name = getattr(contribuyente, "Nombre", None) or None

        if resultado == _RESULT_IDENTIFIED:
            return ResolutionResult(exists=True, official_name=official_name)
        if resultado in (_RESULT_NAME_MISMATCH, _RESULT_NAME_MISMATCH_ALT):
            return ResolutionResult(exists=True, official_name=official_name)
        if resultado.startswith(_RESULT_NOT_IDENTIFIED):
            return ResolutionResult(exists=False, official_name=None)
        raise ResolverUnavailable(f"AEAT devolvió un resultado no reconocido: {resultado!r}")

    async def resolve(self, cif: str, name_read: str | None) -> ResolutionResult:
        return await run_blocking(lambda: self._resolve_sync(cif, name_read), source=self.source)
