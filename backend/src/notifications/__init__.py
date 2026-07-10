"""Módulo de notificaciones: factoría `get_notifier` sobre el seam `Notifier` (S1.4).

El dominio pide `get_notifier()` y le manda `Message`s, sin saber si detrás hay un grabador en
memoria (test/dev) o un transporte SMTP real (futuro). La selección vive aquí, en un único sitio.
"""

from __future__ import annotations

from notifications.notifier import Message, Notifier, RecordingNotifier

__all__ = ["Message", "Notifier", "RecordingNotifier", "get_notifier"]

# Notificador de proceso (singleton perezoso). Se construye una vez y se reutiliza: el grabador en
# memoria debe conservar los mensajes entre la petición y su lectura en las pruebas.
_notifier: Notifier | None = None


def get_notifier() -> Notifier:
    """Devuelve el notificador del proceso (perezoso, reutilizado).

    Sin SMTP configurado (test/dev) es un `RecordingNotifier` en memoria. Cuando se cablee el SMTP
    real (spec S1.4 §6), la selección se hará aquí según la configuración, sin tocar el dominio.
    """
    global _notifier
    if _notifier is None:
        _notifier = _build_notifier()
    return _notifier


def _build_notifier() -> Notifier:
    """Elige el backend de notificación según la configuración.

    Sin `SMTP_HOST` (test/dev, y producción hasta tener credenciales de soporte@autoken.es) se usa
    el grabador en memoria. Con SMTP configurado se fallaría en alto: el transporte real está
    diferido (spec §6) y no debe simularse un envío que no ocurre (regla de oro 8, anti-mentiras).
    """
    from shared.config import get_settings

    if get_settings().smtp_host:
        raise NotImplementedError(
            "Envío SMTP real diferido (spec S1.4 §6): implementa un Notifier SMTP y selecciónalo "
            "aquí. Sin SMTP_HOST se usa el grabador en memoria (RecordingNotifier)."
        )
    return RecordingNotifier()
