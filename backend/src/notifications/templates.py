"""Plantillas de email (PROMPT-AUTOFACTU-AUTH-COMPLETO, bloque 3): texto + HTML sencillo, en
español, con el mismo branding de marca que la app (navy `#021231`, naranja `#FA6703`, texto navy
sobre naranja para AA -- nunca blanco sobre naranja, mismo criterio que el frontend).

Cada función devuelve un `Message` completo. El texto plano (`body`) es la fuente de verdad -- los
tests de `identity.registration`/`identity.password_reset` extraen el token del enlace con una
expresión regular sobre él; el HTML (`html_body`) es solo una presentación más cuidada del MISMO
contenido, nunca información adicional, así que ambos se construyen aquí a la vez, uno al lado del
otro, para que no puedan divergir.
"""

from __future__ import annotations

from notifications.notifier import Message

_BRAND_NAVY = "#021231"
_BRAND_ORANGE = "#FA6703"
_TEXT_MUTED = "#667085"


def _html_wrapper(*, preheader: str, title: str, body_html: str) -> str:
    return (
        '<!doctype html><html lang="es"><body style="margin:0;padding:0;background:#f4f7fb;'
        'font-family:Arial,Helvetica,sans-serif;">'
        f'<span style="display:none;">{preheader}</span>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        '<td align="center" style="padding:24px;">'
        '<table role="presentation" width="100%" style="max-width:480px;background:#ffffff;'
        'border-radius:12px;overflow:hidden;"><tr>'
        f'<td style="background:{_BRAND_NAVY};padding:20px 24px;">'
        '<span style="color:#ffffff;font-size:20px;font-weight:700;">Autofactu</span>'
        "</td></tr><tr>"
        f'<td style="padding:24px;color:#101828;font-size:15px;line-height:1.5;">'
        f'<h1 style="font-size:18px;margin:0 0 12px;">{title}</h1>{body_html}'
        "</td></tr></table></td></tr></table></body></html>"
    )


def _button_html(url: str, label: str) -> str:
    return (
        f'<p style="margin:20px 0;"><a href="{url}" style="background:{_BRAND_ORANGE};'
        f"color:{_BRAND_NAVY};padding:12px 24px;border-radius:999px;text-decoration:none;"
        f'font-weight:700;display:inline-block;">{label}</a></p>'
        f'<p style="font-size:13px;color:{_TEXT_MUTED};">Si el botón no funciona, copia este '
        f'enlace en tu navegador: <a href="{url}">{url}</a></p>'
    )


def registration_pending_admin(
    *, admin_email: str, registrant_email: str, panel_url: str, decision_url: str
) -> Message:
    """Aviso al `tenant_admin`: hay un registro nuevo pendiente de su aprobación, con un enlace
    propio para decidir directamente (2026-09-03, a petición de Julio) o revisarlo en el panel."""
    text = (
        f"El usuario {registrant_email} se ha registrado y está pendiente de tu aprobación.\n\n"
        f"Apruébalo o recházalo directamente aquí: {decision_url}\n\n"
        f"O revísalo en el panel de tu asesoría: {panel_url}"
    )
    html = _html_wrapper(
        preheader=text,
        title="Nuevo registro pendiente de aprobación",
        body_html=(
            f"<p>El usuario <strong>{registrant_email}</strong> se ha registrado y está "
            "pendiente de tu aprobación.</p>"
            + _button_html(decision_url, "Aprobar o rechazar")
            + f'<p style="font-size:13px;color:{_TEXT_MUTED};">También puedes revisarlo en el '
            f'<a href="{panel_url}">panel de tu asesoría</a>.</p>'
        ),
    )
    return Message(
        to=admin_email,
        subject="Nuevo registro pendiente de aprobación",
        body=text,
        html_body=html,
        kind="registration_pending",
    )


def password_reset(*, email: str, url: str, ttl_seconds: int) -> Message:
    """Enlace de restablecimiento de contraseña, tras "olvidé mi contraseña"."""
    minutes = ttl_seconds // 60
    text = (
        "Hemos recibido una solicitud para restablecer tu contraseña. Si has sido tú, abre "
        f"este enlace (caduca en {minutes} minutos): {url}\n\n"
        "Si no has sido tú, puedes ignorar este mensaje: tu contraseña actual sigue siendo válida."
    )
    html = _html_wrapper(
        preheader="Restablece tu contraseña de Autofactu.",
        title="Restablece tu contraseña",
        body_html=(
            "<p>Hemos recibido una solicitud para restablecer tu contraseña.</p>"
            + _button_html(url, "Restablecer contraseña")
            + f'<p style="font-size:13px;color:{_TEXT_MUTED};">Este enlace caduca en {minutes} '
            "minutos.</p>"
            "<p>Si no has sido tú, puedes ignorar este mensaje: tu contraseña actual sigue "
            "siendo válida.</p>"
        ),
    )
    return Message(
        to=email,
        subject="Restablece tu contraseña de Autofactu",
        body=text,
        html_body=html,
        kind="password_reset",
    )


def activation(*, email: str, url: str, ttl_seconds: int) -> Message:
    """Enlace de activación de una cuenta sembrada por un operador (`create_account.py`).

    Hoy `create_account.py` sigue entregando el token por consola, a propósito (mismo criterio de
    "la contraseña nunca pasa por el operador"): esta plantilla queda lista para cuando se decida
    enviarla también por email (pregunta de negocio para Julio, ver informe), sin tener que
    escribirla desde cero entonces.
    """
    hours = ttl_seconds // 3600
    text = (
        "Tu cuenta de Autofactu está lista para activarse. Abre este enlace (caduca en "
        f"{hours} horas) para fijar tu contraseña y activar la verificación en dos pasos: {url}"
    )
    html = _html_wrapper(
        preheader="Activa tu cuenta de Autofactu.",
        title="Activa tu cuenta",
        body_html=(
            "<p>Tu cuenta de Autofactu está lista para activarse.</p>"
            + _button_html(url, "Activar mi cuenta")
            + f'<p style="font-size:13px;color:{_TEXT_MUTED};">Este enlace caduca en {hours} '
            "horas.</p>"
        ),
    )
    return Message(
        to=email,
        subject="Activa tu cuenta de Autofactu",
        body=text,
        html_body=html,
        kind="activation",
    )
