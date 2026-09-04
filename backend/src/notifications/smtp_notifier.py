"""Transporte SMTP real (PROMPT-AUTOFACTU-AUTH-COMPLETO, bloque 3).

Implementa el mismo puerto `Notifier` que `RecordingNotifier`: el dominio (registro, verificación
de email, recuperación de contraseña) no sabe ni le importa cuál de las dos hay detrás -- la elige
`notifications.get_notifier()` según haya o no `SMTP_HOST` configurado.

`send` es SÍNCRONO (mismo contrato que el resto de `Notifier`): `smtplib` es bloqueante, pero quien
llama a `send` desde el hook `after_commit` de SQLAlchemy (síncrono por diseño, ver
`identity.registration._dispatch_after_commit`) ya asume ese coste -- no es nuevo de este backend,
ya lo tenía `RecordingNotifier` (que simplemente no hacía I/O real).
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from notifications.notifier import Message, Notifier

logger = logging.getLogger(__name__)


class SmtpNotifier(Notifier):
    """Envía por SMTP de verdad. `use_tls=True` (587, por defecto) = STARTTLS; `False` (465) = SSL
    directo. Un fallo de envío NUNCA propaga la excepción (F5, defensa en profundidad): el
    registro/reset que disparó el aviso ya se persistió antes de llegar aquí, y un SMTP caído no
    debe tumbar esa petición HTTP ni, en el caso de "olvidé mi contraseña", filtrar por el código
    de respuesta si el email existía o no. Se deja traza en el log (nunca las credenciales) para
    poder diagnosticarlo.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str | None,
        password: str | None,
        sender: str,
        use_tls: bool,
        timeout: float = 10.0,
        blocklist: frozenset[str] | set[str] = frozenset(),
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._sender = sender
        self._use_tls = use_tls
        self._timeout = timeout
        # Lista de bloqueo (Julio, 2026-09-03): dos direcciones de clientes reales recibieron un
        # aviso de una prueba de registro. Filtro a nivel de transporte -- vale para CUALQUIER
        # tipo de mensaje (registro, restablecimiento, activación...), sin tocar el dominio ni el
        # rol de esas cuentas. En minúsculas para que la comparación no distinga mayúsculas.
        self._blocklist = frozenset(email.strip().lower() for email in blocklist if email.strip())

    def send(self, message: Message) -> None:
        if message.to.strip().lower() in self._blocklist:
            logger.info("smtp.send_blocked", extra={"to": message.to, "kind": message.kind})
            return
        mime = self._build_mime(message)
        try:
            if self._use_tls:
                with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                    smtp.starttls()
                    self._authenticate_and_send(smtp, mime, message.to)
            else:
                with smtplib.SMTP_SSL(self._host, self._port, timeout=self._timeout) as smtp:
                    self._authenticate_and_send(smtp, mime, message.to)
        except (OSError, smtplib.SMTPException):
            logger.exception("smtp.send_failed", extra={"to": message.to, "kind": message.kind})

    def _authenticate_and_send(self, smtp: smtplib.SMTP, mime: MIMEMultipart, to: str) -> None:
        if self._user and self._password:
            smtp.login(self._user, self._password)
        smtp.sendmail(self._sender, [to], mime.as_string())

    def _build_mime(self, message: Message) -> MIMEMultipart:
        mime = MIMEMultipart("alternative")
        mime["Subject"] = message.subject
        mime["From"] = self._sender
        mime["To"] = message.to
        # Orden alternative/plain-antes-de-html (RFC 2046 §5.1.4): los clientes que no rendericen
        # HTML se quedan con la última parte que SÍ entienden, el texto plano.
        mime.attach(MIMEText(message.body, "plain", "utf-8"))
        if message.html_body:
            mime.attach(MIMEText(message.html_body, "html", "utf-8"))
        return mime
