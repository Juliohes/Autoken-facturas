"""IP real del cliente para el rate-limit, a prueba de proxy inverso (S1.3 B1).

Pieza compartida por el login (S1.3) y el registro público (S1.4): ambos limitan por IP y necesitan
la MISMA derivación robusta de la IP real, sin duplicarla. Vive fuera del router para que ambos la
reutilicen.
"""

from __future__ import annotations

from fastapi import Request

from shared.config import Settings


def client_ip(request: Request, settings: Settings) -> str:
    """IP real del cliente para el rate-limit, a prueba de proxy inverso (B1).

    `request.client.host` es la IP del **peer directo**: tras Traefik/Caddy sería la del proxy, la
    misma para todos (un fallo de cualquiera bloquearía a toda la plataforma). Se deriva la IP real
    de `X-Forwarded-For` SOLO si la petición viene de un proxy de confianza (`trusted_proxies`);
    nunca se confía en XFF crudo de una fuente no confiable (evita spoofing del rate-limit).
    """
    peer = request.client.host if request.client is not None else "unknown"
    trusted = settings.trusted_proxy_set
    if not trusted:
        return peer  # sin proxies de confianza configurados: la IP es la del peer directo
    trust_all = "*" in trusted
    if not trust_all and peer not in trusted:
        return peer  # la petición no viene de un proxy de confianza: se ignora XFF
    forwarded = [
        p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()
    ]
    if not forwarded:
        return peer
    if trust_all:
        return forwarded[0]  # se confía en toda la cadena: el cliente original es el primero
    for candidate in reversed(forwarded):
        if candidate not in trusted:
            return candidate  # primer salto no-confiable desde la derecha = cliente real
    return forwarded[0]
