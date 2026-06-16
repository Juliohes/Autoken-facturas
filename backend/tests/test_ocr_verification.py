"""Tests de la capa de verificación determinista "tipo DNI" (ADR-0010)."""

from decimal import Decimal

import pytest

from ocr.verification import (
    check_invoice_totals,
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


def test_total_cuadra_con_irpf() -> None:
    lines = [(Decimal(1000), Decimal(210))]
    assert check_invoice_totals(lines, Decimal(1060), irpf_cuota=Decimal(150)).valid


def test_total_multitramo_cuadra() -> None:
    lines = [(Decimal(100), Decimal(21)), (Decimal(200), Decimal(20))]
    assert check_invoice_totals(lines, Decimal(341)).valid


def test_total_descuadra() -> None:
    lines = [(Decimal(100), Decimal(21))]
    assert not check_invoice_totals(lines, Decimal(130)).valid
