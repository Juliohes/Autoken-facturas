"""CLI de alta/baja de cuentas sembradas (sin autoservicio): plataforma y asesoría (migración 0023).

Cierra el hueco que ya avisaba el docstring de `identity/activation.py` ("en producción emite un
script de plataforma" que nunca llegó a versionarse): antes de esta tarea, un `platform_admin` o un
`tenant_admin`/`user` que no pasa por el registro+aprobación autoservicio de S1.4 se creaba con un
INSERT SQL suelto a mano contra la BD real, con el rol superusuario. Este script hace lo mismo por
el único camino legítimo: las funciones `SECURITY DEFINER` de la migración 0023
(`provision_platform_admin`/`provision_tenant_account`/`revoke_platform_admin`), con el rol runtime
restringido de la propia app (`DATABASE_URL` normal, nunca un DSN de admin/superusuario).

La contraseña NUNCA pasa por aquí ni por el operador que ejecuta este script (tabla de secretos del
proyecto: "Contraseñas de login: en ningún sitio, se crean en el primer login"). Cada cuenta creada
queda con `password_hash IS NULL`: el propio dueño de la cuenta completa su activación (S1.3) con el
token de un solo uso que este script imprime, eligiendo él mismo su contraseña.

Uso (desde `backend/`, con el venv activado y `DATABASE_URL`/`REDIS_URL` reales del VPS):
    python scripts/create_account.py platform-admin --email alberto@... [--admin-tech]
    python scripts/create_account.py tenant-account --tenant-slug setex --email x@... \
        --role tenant_admin
    python scripts/create_account.py revoke-platform-admin --email soporte@autoken.es
    python scripts/create_account.py reset-password --email x@... [--tenant-slug setex]
    python scripts/create_account.py reissue-activation --email alberto@...  # token perdido
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from identity import repository
from identity.activation import issue_activation_token
from tenancy.resolution import resolve_tenant


def _print_next_steps(email: str, role: str, token: str, *, host: str) -> None:
    print(f"Cuenta creada: {email} ({role}).")
    print(f"Token de activación de un solo uso (caduca, ver ACTIVATION_TTL): {token}")
    print()
    print(f"Estos DOS pasos los completa la propia persona, ella misma, contra https://{host}:")
    print(f'  1) POST /api/v1/auth/activate  {{"token": "{token}", "password": "<su contraseña>"}}')
    print("     -> devuelve un campo otpauth_uri: escanearlo con una app de 2FA (Authenticator).")
    print(
        f'  2) POST /api/v1/auth/activate/confirm  {{"token": "{token}", '
        '"totp_code": "<código de 6 dígitos de su app>"}'
    )
    print("     -> a partir de aquí ya puede iniciar sesión normalmente.")


async def _platform_admin(email: str, admin_tech: bool) -> None:
    identity = await repository.create_platform_admin_account(email, is_admin_tech=admin_tech)
    token = await issue_activation_token(identity.id)
    _print_next_steps(identity.email, identity.role, token, host="panel-staging.autoken.es")


async def _tenant_account(tenant_slug: str, email: str, role: str) -> None:
    resolved = await resolve_tenant(tenant_slug)
    if resolved is None:
        print(f"No existe ningún tenant activo con slug '{tenant_slug}'.", file=sys.stderr)
        raise SystemExit(2)
    identity = await repository.create_tenant_account(str(resolved.id), email, role)
    token = await issue_activation_token(identity.id)
    _print_next_steps(identity.email, identity.role, token, host=f"{tenant_slug}.autoken.es")


async def _revoke_platform_admin(email: str) -> None:
    revoked_id = await repository.revoke_platform_admin_account(email)
    if revoked_id is None:
        print(f"No había ningún platform_admin activo con email '{email}'.", file=sys.stderr)
        raise SystemExit(1)
    print(f"Revocado: '{email}' (id {revoked_id}) ya no es platform_admin.")


async def _reset_password(email: str, tenant_slug: str | None) -> None:
    tenant_id: str | None = None
    host = "panel-staging.autoken.es"
    if tenant_slug is not None:
        resolved = await resolve_tenant(tenant_slug)
        if resolved is None:
            print(f"No existe ningún tenant activo con slug '{tenant_slug}'.", file=sys.stderr)
            raise SystemExit(2)
        tenant_id = str(resolved.id)
        host = f"{tenant_slug}.autoken.es"

    reset_id = await repository.reset_account_password(email, tenant_id)
    if reset_id is None:
        print(
            f"No había ninguna cuenta activada con email '{email}' en ese ámbito "
            "(o aún no tiene contraseña fijada: eso es reissue-activation, no reset-password).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    token = await issue_activation_token(reset_id)
    _print_next_steps(email, "reseteada", token, host=host)


async def _reissue_activation(email: str) -> None:
    found = await repository.find_platform_admin_for_reissue(email)
    if found is None:
        print(f"No hay ningún platform_admin activo con email '{email}'.", file=sys.stderr)
        raise SystemExit(1)
    user_id, already_activated = found
    if already_activated:
        print(
            f"'{email}' ya completó su activación (tiene contraseña propia): esto no es un token "
            "perdido, es una contraseña olvidada. Usa 'reset-password' en su lugar.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    token = await issue_activation_token(user_id)
    _print_next_steps(email, "platform_admin", token, host="panel-staging.autoken.es")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_admin = sub.add_parser("platform-admin", help="Alta de un platform_admin nuevo")
    p_admin.add_argument("--email", required=True)
    p_admin.add_argument("--admin-tech", action="store_true", help="Marca is_admin_tech (S4.10)")

    p_tenant = sub.add_parser("tenant-account", help="Alta de un tenant_admin/user en un tenant")
    p_tenant.add_argument("--tenant-slug", required=True)
    p_tenant.add_argument("--email", required=True)
    p_tenant.add_argument("--role", required=True, choices=["tenant_admin", "user"])

    p_revoke = sub.add_parser("revoke-platform-admin", help="Baja de un platform_admin existente")
    p_revoke.add_argument("--email", required=True)

    p_reset = sub.add_parser(
        "reset-password", help="Resetea la contraseña de una cuenta ya activada (migración 0024)"
    )
    p_reset.add_argument("--email", required=True)
    p_reset.add_argument(
        "--tenant-slug", help="Omitir para una cuenta platform_admin (sin tenant)"
    )

    p_reissue = sub.add_parser(
        "reissue-activation", help="Reemite el token de un platform_admin que aún no se activó"
    )
    p_reissue.add_argument("--email", required=True)

    args = parser.parse_args()
    try:
        if args.command == "platform-admin":
            asyncio.run(_platform_admin(args.email, args.admin_tech))
        elif args.command == "tenant-account":
            asyncio.run(_tenant_account(args.tenant_slug, args.email, args.role))
        elif args.command == "revoke-platform-admin":
            asyncio.run(_revoke_platform_admin(args.email))
        elif args.command == "reset-password":
            asyncio.run(_reset_password(args.email, args.tenant_slug))
        elif args.command == "reissue-activation":
            asyncio.run(_reissue_activation(args.email))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
