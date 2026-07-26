"""Test de comportamiento de `shared.pg_dsn` (S5.3, hallazgo de auditoría): la contraseña de un DSN
nunca debe acabar como argumento de proceso (`to_pg_cli_args`), y cualquier credencial de estilo URL
que se cuele en un mensaje de error se redacta (`redact_dsn`)."""

from __future__ import annotations

from shared.pg_dsn import redact_dsn, to_libpq_dsn, to_pg_cli_args


def test_to_libpq_dsn_convierte_el_esquema_asyncpg() -> None:
    assert (
        to_libpq_dsn("postgresql+asyncpg://user:pass@host:5432/db")
        == "postgresql://user:pass@host:5432/db"
    )


def test_to_libpq_dsn_deja_intacto_un_dsn_ya_libpq() -> None:
    assert (
        to_libpq_dsn("postgresql://user:pass@host:5432/db") == "postgresql://user:pass@host:5432/db"
    )


def test_to_pg_cli_args_nunca_incluye_la_contrasena_en_los_argumentos() -> None:
    args, env = to_pg_cli_args("postgresql://miusuario:micontraseña-secreta@miservidor:5433/midb")

    assert "micontraseña-secreta" not in args
    assert args == ["-h", "miservidor", "-p", "5433", "-U", "miusuario", "-d", "midb"]
    assert env == {"PGPASSWORD": "micontraseña-secreta"}


def test_to_pg_cli_args_sin_contrasena_no_pone_pgpassword() -> None:
    _args, env = to_pg_cli_args("postgresql://miusuario@miservidor/midb")
    assert env == {}


def test_to_pg_cli_args_sin_puerto_explicito_no_incluye_dash_p() -> None:
    args, _env = to_pg_cli_args("postgresql://user:pass@host/db")
    assert "-p" not in args


def test_redact_dsn_sustituye_credenciales_de_estilo_url() -> None:
    mensaje = 'pg_dump: error de conexión a "postgresql://admin:s3cr3t@host:5432/db"'
    assert "s3cr3t" not in redact_dsn(mensaje)
    assert "postgresql://***:***@host:5432/db" in redact_dsn(mensaje)


def test_redact_dsn_no_toca_texto_sin_credenciales() -> None:
    mensaje = "pg_dump: no se pudo conectar al host miservidor"
    assert redact_dsn(mensaje) == mensaje
