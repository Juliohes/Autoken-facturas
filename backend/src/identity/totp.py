"""Segundo factor TOTP (RFC 6238) con pyotp (S1.3).

TOTP es obligatorio para `platform_admin` y opcional para `tenant_admin`. El secreto vive en
`users.totp_secret` (secreto, nunca al cliente ni a logs); lo único que se devuelve durante la
activación es la URI `otpauth://` para pintar el QR. Se admite una tolerancia de +-1 ventana
(+-30 s) por desfase de reloj (§5 de la spec).
"""

from __future__ import annotations

import pyotp

_TOTP_ISSUER = "Autoken Facturas"


def generate_secret() -> str:
    """Genera un secreto TOTP nuevo en base32 (para enrolar un segundo factor)."""
    return pyotp.random_base32()


def verify_code(secret: str, code: str, *, valid_window: int = 1) -> bool:
    """True si `code` vale para `secret` ahora (con +-`valid_window` ventanas de tolerancia)."""
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=valid_window)
    except (ValueError, TypeError):
        return False


def provisioning_uri(secret: str, account_name: str) -> str:
    """URI `otpauth://totp/...` para pintar el QR de enrolado en la app de autenticación."""
    return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=_TOTP_ISSUER)
