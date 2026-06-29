"""Tests de la capa de verificación determinista "tipo DNI" (ADR-0010)."""

from decimal import Decimal

import pytest

from ocr.verification import (
    check_tax_line,
    validate_cif,
    validate_iban,
    validate_nie,
    validate_nif,
    validate_tax_id,
)

# --- NIF -----------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["12345678Z", "12345678-Z", "12345678 z"])
def test_nif_valido(value: str) -> None:
    assert validate_nif(value).valid


def test_nif_letra_incorrecta() -> None:
    result = validate_nif("12345678A")
    assert not result.valid
    assert "control" in result.reason.lower()


def test_nif_formato_invalido() -> None:
    assert not validate_nif("1234A").valid


# --- NIE -----------------------------------------------------------------------------------


def test_nie_valido() -> None:
    assert validate_nie("X1234567L").valid


def test_nie_letra_incorrecta() -> None:
    assert not validate_nie("X1234567M").valid


# --- CIF -----------------------------------------------------------------------------------


def test_cif_valido_control_numerico() -> None:
    assert validate_cif("A58818501").valid


def test_cif_valido_control_letra() -> None:
    # Tipo "P" exige que el control sea letra.
    assert validate_cif("P1234567D").valid


def test_cif_control_incorrecto() -> None:
    assert not validate_cif("A58818502").valid


def test_cif_formato_invalido() -> None:
    assert not validate_cif("158818501").valid  # no empieza por letra de tipo


# BP-2: las claves N (entidades extranjeras), W (establecimientos permanentes) y R
# (congregaciones) admiten control NUMÉRICO o LETRA. Las fuentes oficiales son contradictorias
# y la implementación de referencia (python-stdnum) acepta ambos; exigir letra rechazaría CIFs
# válidos. Cuerpo "1234567": dígito de control 4, letra de control "D".
@pytest.mark.parametrize("org", ["N", "W", "R"])
@pytest.mark.parametrize("control", ["4", "D"])
def test_cif_tipo_ambiguo_acepta_control_numerico_o_letra(org: str, control: str) -> None:
    assert validate_cif(f"{org}1234567{control}").valid


def test_cif_tipo_letra_exige_letra() -> None:
    # Clave "P": el control correcto es la letra "D"; el dígito numérico equivalente NO vale.
    assert validate_cif("P1234567D").valid
    assert not validate_cif("P12345674").valid


def test_cif_clave_k_no_es_tipo_cif() -> None:
    # "K" es un NIF especial de persona física, no una clave de CIF: se rechaza por formato.
    result = validate_cif("K1234567D")
    assert not result.valid
    assert "formato" in result.reason.lower()


# --- Dispatcher ----------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["12345678Z", "X1234567L", "A58818501"])
def test_validate_tax_id_detecta_tipo(value: str) -> None:
    assert validate_tax_id(value).valid


def test_validate_tax_id_vacio() -> None:
    assert not validate_tax_id("   ").valid


# --- IBAN ----------------------------------------------------------------------------------


def test_iban_espanol_valido() -> None:
    assert validate_iban("ES9121000418450200051332").valid


def test_iban_espanol_con_espacios() -> None:
    assert validate_iban("ES91 2100 0418 4502 0005 1332").valid


def test_iban_checksum_incorrecto() -> None:
    assert not validate_iban("ES9121000418450200051333").valid


def test_iban_longitud_espanola_incorrecta() -> None:
    assert not validate_iban("ES912100041845020005").valid


def test_iban_otro_pais_sin_filtro() -> None:
    # IBAN alemán válido; con country=None no se exige prefijo ES.
    assert validate_iban("DE89370400440532013000", country=None).valid
    assert not validate_iban("DE89370400440532013000").valid  # por defecto exige ES


# --- Cuadre aritmético ---------------------------------------------------------------------


def test_tramo_cuadra() -> None:
    assert check_tax_line(Decimal(100), Decimal(21), Decimal("21.00")).valid


def test_tramo_dentro_de_tolerancia() -> None:
    assert check_tax_line(Decimal("99.99"), Decimal(21), Decimal("21.00")).valid


def test_tramo_descuadra() -> None:
    result = check_tax_line(Decimal(100), Decimal(21), Decimal(25))
    assert not result.valid
    assert "descuadre" in result.reason.lower()


# Los tests de cuadre global migraron a test_ocr_cuadre.py con la nueva firma TaxLine (spec BP-1).
