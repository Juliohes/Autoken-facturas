"""Resolver VIES (L3, verificación de VAT intra-UE; no autoritativo para lo nacional).

Adaptador del servicio público `checkVatApprox` de la Comisión Europea (SOAP). En S2.8 la capa L1
(`shared.tax_id.validate_tax_id`) solo admite identificadores **españoles** (NIF/NIE/CIF): el CIF
que llega a VIES es siempre nacional, así que se consulta con `countryCode="ES"`. Un `exists=True`
para un ES es un `valid` legítimo (operador en el ROI); un `exists=False` **no** invalida
(`negative_authoritative=False`), porque muchos operadores nacionales válidos no están en el ROI:
el servicio no lo trata como `not_found` y deja mandar a la fuente autoritativa (AEAT).

La verificación de contrapartes **intra-UE no españolas queda DIFERIDA** (ver ADR-0011 y spec §5):
requeriría que L1 aceptara el formato VAT-UE (país + número) para no bloquear antes. No se codifica
como si existiera.

En CI va doblado (sin red). La llamada real solo se ejerce en staging.
"""

from __future__ import annotations

from typing import Any

from shared.config import Settings

from .base import ResolutionResult, ResolverUnavailable, run_blocking

# L1 garantiza que el CIF que llega es español; VIES se consulta siempre con país "ES".
_COUNTRY = "ES"


class ViesResolver:
    """Fuente VIES (`checkVatApprox`) tras la interfaz `CifResolver`.

    El cliente SOAP (zeep) es bloqueante: la llamada corre en un hilo vía `run_blocking`, que
    traduce los fallos a `ResolverUnavailable` con log. El cliente se construye una vez de forma
    perezosa y se reutiliza. El VIES cae a menudo; su indisponibilidad degrada a `unverified`.
    """

    source = "vies"
    negative_authoritative = False

    def __init__(self, settings: Settings) -> None:
        if not settings.vies_endpoint:
            raise ResolverUnavailable("VIES no configurado (falta vies_endpoint)")
        self._endpoint = settings.vies_endpoint
        self._timeout = settings.vies_timeout
        self._client: Any = None  # cliente zeep perezoso (se construye una vez, se reutiliza)

    def _build_client(self) -> Any:
        """Construye el cliente SOAP (bloqueante: parsea el WSDL). Solo en staging."""
        from zeep import Client
        from zeep import Settings as ZeepSettings
        from zeep.transports import Transport

        transport = Transport(timeout=self._timeout, operation_timeout=self._timeout)
        # XXE explícito (belt-and-suspenders): sin DTD, sin entidades, sin recursos externos.
        zeep_settings = ZeepSettings(forbid_dtd=True, forbid_entities=True, forbid_external=True)
        return Client(self._endpoint, transport=transport, settings=zeep_settings)

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _resolve_sync(self, cif: str, name_read: str | None) -> ResolutionResult:
        client = self._get_client()
        response = client.service.checkVatApprox(
            countryCode=_COUNTRY, vatNumber=cif.strip().upper(), traderName=name_read or None
        )
        valid = bool(getattr(response, "valid", False))
        official_name = getattr(response, "traderName", None) or None
        return ResolutionResult(exists=valid, official_name=official_name)

    async def resolve(self, cif: str, name_read: str | None) -> ResolutionResult:
        return await run_blocking(lambda: self._resolve_sync(cif, name_read), source=self.source)
