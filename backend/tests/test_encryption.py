"""Tests de comportamiento S5.2 (fundamentos de cifrado): derivación de claves por tenant e índice
ciego, sin tocar Postgres todavía (eso lo cubren los tests de cada repositorio).

Spec: docs/specs/S5.2-cifrado-por-tenant.md, invariantes §4.
"""

from __future__ import annotations

from shared.encryption import blind_index, derive_tenant_encryption_key, derive_tenant_index_key

_MASTER_KEY = "clave-maestra-de-prueba-suficientemente-larga-123456"  # gitleaks:allow (test)


def test_la_clave_de_cifrado_es_deterministica_para_el_mismo_tenant() -> None:
    """Misma clave maestra + mismo tenant -> misma clave de cifrado siempre (se recalcula, no se
    guarda)."""
    a = derive_tenant_encryption_key(_MASTER_KEY, "tenant-a")
    b = derive_tenant_encryption_key(_MASTER_KEY, "tenant-a")
    assert a == b


def test_la_clave_de_cifrado_difiere_entre_tenants() -> None:
    """Dos tenants distintos -> claves de cifrado distintas, aunque compartan la clave maestra."""
    a = derive_tenant_encryption_key(_MASTER_KEY, "tenant-a")
    b = derive_tenant_encryption_key(_MASTER_KEY, "tenant-b")
    assert a != b


def test_la_clave_de_indice_es_distinta_de_la_de_cifrado_para_el_mismo_tenant() -> None:
    """Invariante §4: nunca la misma clave para cifrar que para el índice ciego, ni siquiera del
    mismo tenant."""
    encryption_key = derive_tenant_encryption_key(_MASTER_KEY, "tenant-a")
    index_key = derive_tenant_index_key(_MASTER_KEY, "tenant-a")
    assert encryption_key != index_key.hex()


def test_el_indice_ciego_es_deterministico_para_el_mismo_valor_y_tenant() -> None:
    """El mismo CIF normalizado, del mismo tenant, produce siempre el mismo índice (permite
    WHERE/UNIQUE por igualdad exacta sin descifrar)."""
    a = blind_index(_MASTER_KEY, "tenant-a", "A39031620")
    b = blind_index(_MASTER_KEY, "tenant-a", "A39031620")
    assert a == b


def test_el_indice_ciego_difiere_para_valores_distintos_del_mismo_tenant() -> None:
    a = blind_index(_MASTER_KEY, "tenant-a", "A39031620")
    b = blind_index(_MASTER_KEY, "tenant-a", "B06183446")
    assert a != b


def test_el_indice_ciego_difiere_entre_tenants_para_el_mismo_cif() -> None:
    """Aunque dos tenants tuvieran el mismo CIF real, sus índices ciegos no se correlacionan entre
    sí (cada uno deriva con su propia clave) — no hace falta para el UNIQUE (ya va acotado por
    tenant_id), pero evita filtrar por coincidencia que dos tenants comparten proveedor."""
    a = blind_index(_MASTER_KEY, "tenant-a", "A39031620")
    b = blind_index(_MASTER_KEY, "tenant-b", "A39031620")
    assert a != b
