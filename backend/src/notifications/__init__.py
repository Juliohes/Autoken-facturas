"""Módulo de notificaciones: factoría `get_notifier` sobre el seam `Notifier` (S1.4, bloque 3 de
PROMPT-AUTOFACTU-AUTH-COMPLETO.md).

El dominio pide `get_notifier()` y le manda `Message`s, sin saber si detrás hay un grabador en
memoria (test/dev, sin `SMTP_HOST`) o un transporte SMTP real (`SmtpNotifier`, con `SMTP_HOST`
configurado). La selección vive aquí, en un único sitio.
"""

from __future__ import annotations

from notifications.notifier import Message, Notifier, RecordingNotifier

__all__ = ["Message", "Notifier", "RecordingNotifier", "get_notifier"]

# Notificador de proceso (singleton perezoso). Se construye una vez y se reutiliza: el grabador en
# memoria debe conservar los mensajes entre la petición y su lectura en las pruebas.
_notifier: Notifier | None = None


def get_notifier() -> Notifier:
    """Devuelve el notificador del proceso (perezoso, reutilizado).

    Sin `SMTP_HOST` (test/dev, y producción hasta tener credenciales de soporte@autoken.es) es un
    `RecordingNotifier` en memoria: no rompe nada, pero no envía ningún email de verdad. Con
    `SMTP_HOST` configurado es un `SmtpNotifier` de verdad.
    """
    global _notifier
    if _notifier is None:
        _notifier = _build_notifier()
    return _notifier


def _build_notifier() -> Notifier:
    """Elige el backend de notificación según la configuración."""
    from shared.config import get_settings

    settings = get_settings()
    if settings.smtp_host:
        from notifications.smtp_notifier import SmtpNotifier

        return SmtpNotifier(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user,
            password=settings.smtp_password,
            sender=settings.smtp_from or settings.smtp_host,
            use_tls=settings.smtp_use_tls,
        )
    return RecordingNotifier()
