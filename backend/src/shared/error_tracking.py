"""Captura de errores en producción vía Sentry (S5.6).

Se activa SOLO si `SENTRY_DSN` está configurado (mismo criterio que el resto de proveedores
externos opcionales del proyecto): sin DSN, `init_sentry` no hace nada — ni intento de red, ni
coste, ni riesgo de tumbar el arranque de la app por su culpa (fail-open para observabilidad: perder
trazas de error es aceptable, perder el servicio entero no lo es, spec §4).

`send_default_pii=False` y `max_request_body_size="never"` van explícitos, no heredados del default
del SDK (auditoría de seguridad): esta es una app fiscal multi-tenant, con contenido de facturas y
credenciales/códigos en las peticiones a `/auth/*` — no basta con confiar en que una versión futura
de `sentry-sdk` mantenga el mismo valor por defecto. Julio aún no tiene cuenta de Sentry (spec §0);
cuando la cree, usar una región UE, coherente con la decisión de residencia de datos del proyecto.
"""

from __future__ import annotations

from shared.config import Settings


def init_sentry(settings: Settings) -> None:
    """Inicializa el SDK de Sentry si `settings.sentry_dsn` está configurado; si no, no hace
    nada."""
    if not settings.sentry_dsn:
        return

    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env.value,
        send_default_pii=False,
        max_request_body_size="never",
    )
