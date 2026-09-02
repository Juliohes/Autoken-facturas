"""Tests de comportamiento: plantillas de email y transporte SMTP (PROMPT-AUTOFACTU-AUTH-COMPLETO,
bloque 3). No golpea ningún SMTP real: `SmtpNotifier` se prueba sustituyendo `smtplib.SMTP`/
`smtplib.SMTP_SSL` por un doble de prueba que solo registra las llamadas.
"""

from __future__ import annotations

import smtplib
from email import message_from_string

import pytest

from notifications import templates
from notifications.smtp_notifier import SmtpNotifier


class _FakeSmtp:
    """Doble de `smtplib.SMTP`/`smtplib.SMTP_SSL`: registra llamadas, no abre ningún socket."""

    last_instance: _FakeSmtp | None = None

    def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.logins: list[tuple[str, str]] = []
        self.sent: list[tuple[str, list[str], str]] = []
        _FakeSmtp.last_instance = self

    def __enter__(self) -> _FakeSmtp:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, user: str, password: str) -> None:
        self.logins.append((user, password))

    def sendmail(self, sender: str, recipients: list[str], message: str) -> None:
        self.sent.append((sender, recipients, message))


class _FailingFakeSmtp(_FakeSmtp):
    def sendmail(self, sender: str, recipients: list[str], message: str) -> None:
        raise smtplib.SMTPServerDisconnected("boom")


# --- Plantillas ------------------------------------------------------------------------------


def test_registration_pending_admin_incluye_el_email_del_registrante() -> None:
    msg = templates.registration_pending_admin(
        admin_email="admin@ilex.es", registrant_email="nuevo@correo.es"
    )
    assert msg.to == "admin@ilex.es"
    assert msg.kind == "registration_pending"
    assert "nuevo@correo.es" in msg.body
    assert msg.html_body and "nuevo@correo.es" in msg.html_body


def test_email_verification_incluye_el_enlace_en_texto_y_html() -> None:
    url = "https://ilex.autoken.es/registro/confirmar?token=abc123"
    msg = templates.email_verification(email="nuevo@correo.es", url=url, ttl_seconds=86400)
    assert msg.to == "nuevo@correo.es"
    assert msg.kind == "email_verification"
    assert url in msg.body
    assert msg.html_body and url in msg.html_body
    assert "24 horas" in msg.body


def test_password_reset_incluye_el_enlace_y_los_minutos_de_caducidad() -> None:
    url = "https://ilex.autoken.es/restablecer?token=abc123"
    msg = templates.password_reset(email="ana@ilex.es", url=url, ttl_seconds=3600)
    assert msg.to == "ana@ilex.es"
    assert msg.kind == "password_reset"
    assert url in msg.body
    assert msg.html_body and url in msg.html_body
    assert "60 minutos" in msg.body


def test_activation_incluye_el_enlace() -> None:
    url = "https://ilex.autoken.es/activar?token=abc123"
    msg = templates.activation(email="ana@ilex.es", url=url, ttl_seconds=259200)
    assert msg.to == "ana@ilex.es"
    assert msg.kind == "activation"
    assert url in msg.body
    assert msg.html_body and url in msg.html_body


# --- SmtpNotifier ------------------------------------------------------------------------------


def _notifier(**overrides: object) -> SmtpNotifier:
    defaults: dict[str, object] = {
        "host": "smtp.hostinger.com",
        "port": 587,
        "user": "soporte@autoken.es",
        "password": "un-secreto",  # gitleaks:allow
        "sender": "Autofactu <soporte@autoken.es>",
        "use_tls": True,
    }
    defaults.update(overrides)
    return SmtpNotifier(**defaults)  # type: ignore[arg-type]


def test_smtp_notifier_con_starttls_hace_starttls_login_y_envia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtplib, "SMTP", _FakeSmtp)
    notifier = _notifier(use_tls=True, port=587)

    msg = templates.password_reset(email="ana@ilex.es", url="https://x/y", ttl_seconds=60)
    notifier.send(msg)

    fake = _FakeSmtp.last_instance
    assert fake is not None
    assert fake.host == "smtp.hostinger.com"
    assert fake.port == 587
    assert fake.started_tls is True
    assert fake.logins == [("soporte@autoken.es", "un-secreto")]
    assert len(fake.sent) == 1
    sender, recipients, raw = fake.sent[0]
    assert sender == "Autofactu <soporte@autoken.es>"
    assert recipients == ["ana@ilex.es"]
    # El mensaje MIME puede venir codificado (base64/quoted-printable): se decodifica para
    # comprobar que el enlace viaja de verdad, tanto en la parte de texto como en la de HTML.
    parsed = message_from_string(raw)
    parts = {
        part.get_content_type(): part.get_payload(decode=True).decode("utf-8")
        for part in parsed.walk()
        if part.get_content_maintype() == "text"
    }
    assert "https://x/y" in parts["text/plain"]
    assert "https://x/y" in parts["text/html"]


def test_smtp_notifier_con_ssl_directo_no_hace_starttls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSmtp)
    notifier = _notifier(use_tls=False, port=465)

    notifier.send(templates.password_reset(email="ana@ilex.es", url="https://x/y", ttl_seconds=60))

    fake = _FakeSmtp.last_instance
    assert fake is not None
    assert fake.port == 465
    assert fake.started_tls is False  # SSL directo: no hace falta STARTTLS
    assert len(fake.sent) == 1


def test_smtp_notifier_sin_credenciales_no_hace_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP", _FakeSmtp)
    notifier = _notifier(user=None, password=None)

    notifier.send(templates.password_reset(email="ana@ilex.es", url="https://x/y", ttl_seconds=60))

    fake = _FakeSmtp.last_instance
    assert fake is not None
    assert fake.logins == []
    assert len(fake.sent) == 1


def test_smtp_notifier_no_propaga_el_fallo_de_envio(monkeypatch: pytest.MonkeyPatch) -> None:
    """F5: un SMTP caído no debe tumbar la petición HTTP que disparó el aviso."""
    monkeypatch.setattr(smtplib, "SMTP", _FailingFakeSmtp)
    notifier = _notifier()

    notifier.send(templates.password_reset(email="ana@ilex.es", url="https://x/y", ttl_seconds=60))
    # Si `send` hubiera relanzado, este test ya habría fallado antes de llegar aquí.


# --- Factoría ------------------------------------------------------------------------------
# `_build_notifier` se prueba directamente (no `get_notifier`, que cachea en un singleton global
# de proceso compartido con el resto de la suite -- contaminarlo rompería cualquier otro test que
# dependa de `RecordingNotifier`).


def test_sin_smtp_host_la_factoria_elige_el_grabador_en_memoria(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from notifications import RecordingNotifier, _build_notifier
    from shared import config

    monkeypatch.delenv("SMTP_HOST", raising=False)
    config.get_settings.cache_clear()
    try:
        assert isinstance(_build_notifier(), RecordingNotifier)
    finally:
        config.get_settings.cache_clear()


def test_con_smtp_host_la_factoria_elige_smtp_notifier(monkeypatch: pytest.MonkeyPatch) -> None:
    from notifications import _build_notifier
    from shared import config

    monkeypatch.setenv("SMTP_HOST", "smtp.hostinger.com")
    config.get_settings.cache_clear()
    try:
        assert isinstance(_build_notifier(), SmtpNotifier)
    finally:
        monkeypatch.delenv("SMTP_HOST", raising=False)
        config.get_settings.cache_clear()
