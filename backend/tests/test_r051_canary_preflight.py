"""Pruebas de comportamiento del preflight de canario R-051."""

from __future__ import annotations

from pathlib import Path

from scripts.r051_canary_preflight import _read_env_file, preflight_environment


def _environment() -> dict[str, str]:
    return {
        "SCANNER_V2_ENABLED": "true",
        "CONTINUOUS_CAPTURE_ENABLED": "true",
        "REVIEW_INBOX_ENABLED": "true",
        "DRAFT_AUTOSAVE_ENABLED": "true",
        "PROCESSING_STAGES_ENABLED": "true",
        "OCR_POLICY_V2_ENABLED": "true",
        "SUPPLIER_LEARNING_ENABLED": "true",
        "ROLLOUT_TENANT_ALLOWLIST": '["00000000-0000-0000-0000-000000000001"]',
        "GRAFANA_ADMIN_PASSWORD": "secret-no-debe-aparecer",
        "DB_ENCRYPTION_MASTER_KEY": "secret-no-debe-aparecer",
        "POSTGRES_APP_PASSWORD": "secret-no-debe-aparecer",
    }


def test_preflight_valido_no_publica_secretos() -> None:
    report = preflight_environment(_environment())

    assert report.ready is True
    rendered = str(report.to_dict())
    assert "secret-no-debe-aparecer" not in rendered
    assert all(check.status == "ok" for check in report.checks)


def test_preflight_rechaza_flag_no_booleano_y_allowlist_invalida() -> None:
    environment = _environment()
    environment["OCR_POLICY_V2_ENABLED"] = "maybe"
    environment["ROLLOUT_TENANT_ALLOWLIST"] = "not-json"

    report = preflight_environment(environment)

    assert report.ready is False
    assert {check.name for check in report.checks if check.status == "error"} == {
        "feature_flags",
        "tenant_allowlist",
    }


def test_preflight_informa_de_secretos_de_staging_ausentes_sin_valores() -> None:
    environment = _environment()
    del environment["POSTGRES_APP_PASSWORD"]

    report = preflight_environment(environment)

    assert report.ready is False
    secret_check = next(check for check in report.checks if check.name == "staging_secrets")
    assert secret_check.status == "error"
    assert "POSTGRES_APP_PASSWORD" in secret_check.detail


def test_preflight_puede_leer_un_dotenv_sin_confundir_comentarios(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comentario\nSCANNER_V2_ENABLED=false\nROLLOUT_TENANT_ALLOWLIST=[]\n",
        encoding="utf-8",
    )

    values = _read_env_file(env_file)

    assert values["SCANNER_V2_ENABLED"] == "false"
    assert values["ROLLOUT_TENANT_ALLOWLIST"] == "[]"
