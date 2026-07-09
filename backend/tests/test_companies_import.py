"""Tests de comportamiento S1.5: importador del Excel de empresas (spec docs/specs/S1.5).

Criterios C9-C12. `POST /companies/import` recibe un `.xlsx` (multipart) y devuelve un informe:
creadas, filas inválidas (fila + motivo) y duplicadas omitidas. Regla: fila = todo-o-nada.
El fichero tiene éxito parcial. Fase roja: el endpoint de importación aún no existe.
"""

from __future__ import annotations

import httpx
import pytest

from tests._auth import bearer, host
from tests._companies import (
    COMPANIES,
    IMPORT,
    INVALID_TAXID,
    REAL_XLSX,
    VALID_CIF,
    VALID_CIF_2,
    VALID_NIF,
    XLSX_MIME,
    admin_token,
    build_xlsx,
    seed_admin,
)
from tests._dbtest import seed_company

Api = tuple[httpx.AsyncClient, dict[str, str]]


def _auth(token: str) -> dict[str, str]:
    return {**host("ilex.localhost"), **bearer(token)}


async def test_c9_importar_excel_valido_crea_todas(authapi: Api) -> None:
    """C9: importar el Excel de Setex (60 filas válidas) -> 60 creadas (active), sin errores."""
    client, dsns = authapi
    await seed_admin(dsns)
    token = await admin_token(client)
    with open(REAL_XLSX, "rb") as fh:
        contenido = fh.read()
    resp = await client.post(
        IMPORT,
        files={"file": ("Empresas_CIF_NIF.xlsx", contenido, XLSX_MIME)},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    informe = resp.json()
    assert informe["created"] == 60
    assert informe["invalid"] == []
    assert informe["duplicates"] == []
    lista = await client.get(COMPANIES, headers=_auth(token))
    assert len(lista.json()) == 60


async def test_c10_exito_parcial_reporta_las_invalidas(authapi: Api) -> None:
    """C10: las válidas entran; las inválidas se reportan (fila + motivo); ninguna a medias."""
    client, dsns = authapi
    await seed_admin(dsns)
    token = await admin_token(client)
    xlsx = build_xlsx(
        [
            ("Buena SL", VALID_CIF),  # válida
            ("CIF malo", INVALID_TAXID),  # dígito de control inválido
            ("Sin CIF", ""),  # falta CIF
            ("", VALID_NIF),  # falta nombre
            ("Otra Buena", VALID_CIF_2),  # válida
        ]
    )
    resp = await client.post(
        IMPORT, files={"file": ("x.xlsx", xlsx, XLSX_MIME)}, headers=_auth(token)
    )
    assert resp.status_code == 200
    informe = resp.json()
    assert informe["created"] == 2
    assert informe["duplicates"] == []
    assert len(informe["invalid"]) == 3
    for entrada in informe["invalid"]:
        assert "row" in entrada and "reason" in entrada
    lista = await client.get(COMPANIES, headers=_auth(token))
    assert {c["cif"] for c in lista.json()} == {VALID_CIF, VALID_CIF_2}  # solo las 2 válidas


async def test_c11_duplicados_se_omiten_idempotente(authapi: Api) -> None:
    """C11: una fila con CIF ya existente se omite (no error); re-importar es idempotente."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    await seed_company(dsns["admin"], tenant_id=tid, name="Ya existe", cif=VALID_CIF)
    token = await admin_token(client)
    filas = [("Dup", VALID_CIF), ("Nueva", VALID_CIF_2)]

    primera = await client.post(
        IMPORT, files={"file": ("x.xlsx", build_xlsx(filas), XLSX_MIME)}, headers=_auth(token)
    )
    assert primera.status_code == 200
    rep1 = primera.json()
    assert rep1["created"] == 1
    assert len(rep1["duplicates"]) == 1
    assert rep1["invalid"] == []

    segunda = await client.post(
        IMPORT, files={"file": ("x.xlsx", build_xlsx(filas), XLSX_MIME)}, headers=_auth(token)
    )
    rep2 = segunda.json()
    assert rep2["created"] == 0
    assert len(rep2["duplicates"]) == 2  # ambas ya existen ahora


async def test_c12_fichero_mal_formado_se_maneja_con_control(authapi: Api) -> None:
    """C12: no-xlsx / sin columnas -> 400 controlado; solo cabecera -> 200 con 0 creadas."""
    client, dsns = authapi
    await seed_admin(dsns)
    token = await admin_token(client)

    no_xlsx = await client.post(
        IMPORT,
        files={"file": ("x.txt", b"esto no es un excel", "text/plain")},
        headers=_auth(token),
    )
    assert no_xlsx.status_code == 400

    sin_columnas = build_xlsx([("uno", "dos", "tres")], header=("A", "B", "C"))
    malas_cols = await client.post(
        IMPORT, files={"file": ("x.xlsx", sin_columnas, XLSX_MIME)}, headers=_auth(token)
    )
    assert malas_cols.status_code == 400

    solo_cabecera = build_xlsx([])
    vacio = await client.post(
        IMPORT, files={"file": ("x.xlsx", solo_cabecera, XLSX_MIME)}, headers=_auth(token)
    )
    assert vacio.status_code == 200
    assert vacio.json()["created"] == 0


async def test_m1_fichero_por_encima_del_limite_se_rechaza(
    authapi: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M1: un fichero por encima del tope de tamaño -> 413, antes de parsear (guardarraíl anti-DoS).

    El tope se inyecta pequeño por setting para no construir un fichero gigante: cualquier `.xlsx`
    real (varios KB) ya lo supera.
    """
    from shared import config

    client, dsns = authapi
    await seed_admin(dsns)
    token = await admin_token(client)
    monkeypatch.setenv("COMPANIES_IMPORT_MAX_BYTES", "100")
    config.get_settings.cache_clear()

    xlsx = build_xlsx([("Buena SL", VALID_CIF)])
    resp = await client.post(
        IMPORT, files={"file": ("x.xlsx", xlsx, XLSX_MIME)}, headers=_auth(token)
    )
    assert resp.status_code == 413
    assert (await client.get(COMPANIES, headers=_auth(token))).json() == []  # no se importó nada

    config.get_settings.cache_clear()


async def test_m1_tope_de_filas_corta_y_marca_truncado(
    authapi: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M1: el parseo corta al tope de filas; crea solo hasta el tope y marca el informe truncado."""
    from shared import config

    client, dsns = authapi
    await seed_admin(dsns)
    token = await admin_token(client)
    monkeypatch.setenv("COMPANIES_IMPORT_MAX_ROWS", "2")
    config.get_settings.cache_clear()

    xlsx = build_xlsx([("Una", VALID_CIF), ("Dos", VALID_CIF_2), ("Tres", VALID_NIF)])
    resp = await client.post(
        IMPORT, files={"file": ("x.xlsx", xlsx, XLSX_MIME)}, headers=_auth(token)
    )
    assert resp.status_code == 200
    informe = resp.json()
    assert informe["created"] == 2  # solo las 2 primeras filas de datos
    assert informe["truncated"] is True
    lista = await client.get(COMPANIES, headers=_auth(token))
    assert len(lista.json()) == 2  # la 3.ª fila ni se parseó ni se creó

    config.get_settings.cache_clear()
