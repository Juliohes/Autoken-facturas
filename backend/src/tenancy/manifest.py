"""Construcción del Web App Manifest por tenant (S4.3): mapeo puro branding -> manifest.

Sin HTTP ni SQL, para que el mapeo sea testeable sin BD (mismo criterio de separación que
`frontend/src/features/tenancy/theme.ts`, S4.2: lógica pura aparte del acceso a datos y del router).
El backend nunca inventa un valor de branding (spec S4.2 decisión 1, reafirmada en S4.3): sin
`app_name`/`logo_url`, se cae a los valores por defecto ya existentes hoy (el manifest fijo que
generaba `vite-plugin-pwa`), nunca a un valor inventado.
"""

from __future__ import annotations

from tenancy.repository import TenantBranding

# Espejo de `frontend/src/features/tenancy/theme.ts` (`DEFAULT_APP_NAME`/`DEFAULT_COLOR_SECONDARY`,
# S4.2): mismo valor por defecto, dos dominios distintos (manifest de instalación vs tema de la SPA
# en ejecución) que hoy coinciden por diseño, no por una fuente compartida (Python/TS no la tienen).
# Si se cambia el color/nombre de marca por defecto en un sitio, revisar también el otro.
DEFAULT_APP_NAME = "Autoken Facturas"
DEFAULT_SHORT_NAME = "Facturas"
DEFAULT_COLOR = "#0f172a"

# Recomendación del estándar de Web App Manifest: short_name legible en un icono de pantalla de
# inicio.
_SHORT_NAME_MAX_LENGTH = 12

# Mismos 3 iconos que generaba `vite-plugin-pwa` (`frontend/vite.config.ts`, hasta esta tarea): se
# mantienen como fallback cuando el tenant no tiene `logo_url` (spec S4.3 decisión 3). Rutas con `/`
# inicial a propósito: un `src` de icono relativo se resuelve contra la URL del PROPIO manifest (no
# contra la del documento HTML), y el manifest ya no vive en la raíz sino en
# `/api/v1/manifest.webmanifest`; sin el `/` inicial resolverían a `/api/v1/icons/...` (404, los
# iconos son estáticos del frontend, servidos en `/icons/...`).
_DEFAULT_ICONS: list[dict[str, str]] = [
    {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
    {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
]


def build_manifest(branding: TenantBranding | None) -> dict[str, object]:
    """Manifest del tenant: su nombre/color/icono si tiene branding, los de hoy si no.

    `short_name` truncado a 12 caracteres solo cuando hay `app_name` propio (spec §5, caso límite);
    el `short_name` por defecto sigue siendo el fijo de hoy (`"Facturas"`), no una versión recortada
    del nombre largo por defecto.
    """
    tenant_app_name = branding.app_name if branding is not None else None
    tenant_color = branding.color_secondary if branding is not None else None
    tenant_logo = branding.logo_url if branding is not None else None

    if tenant_app_name:
        name = tenant_app_name
        short_name = name[:_SHORT_NAME_MAX_LENGTH]
    else:
        name = DEFAULT_APP_NAME
        short_name = DEFAULT_SHORT_NAME

    color = tenant_color or DEFAULT_COLOR
    icons = [{"src": tenant_logo, "sizes": "any"}] if tenant_logo else _DEFAULT_ICONS

    return {
        "name": name,
        "short_name": short_name,
        "description": "Digitalización de facturas con OCR/IA",
        "theme_color": color,
        "background_color": color,
        "display": "standalone",
        "start_url": "/",
        "icons": icons,
    }
