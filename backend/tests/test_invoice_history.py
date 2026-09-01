"""Regresiones mínimas del historial privado S6.12.

Los escenarios de corte a veinte, estados pendientes/fallidos, privacidad entre compañeros y visión
de asesoría viven en ``test_multipage_intake_history.py``. Este módulo conserva las guardas HTTP que
no dependen de una factura confirmada.
"""

from __future__ import annotations

import httpx

from tests._intake import auth, seed_uploader, token_for
from tests._invoicing import history_url, seed_invoice

Api = tuple[httpx.AsyncClient, dict[str, str]]


async def test_historial_vacio_responde_200_con_lista_vacia(authapi: Api) -> None:
    """Sin ningún documento aceptado, el historial es una lista vacía y no un 404."""
    client, dsns = authapi
    await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    response = await client.get(history_url(), headers=auth(token))

    assert response.status_code == 200, response.text
    assert response.json() == {"entries": []}


async def test_historial_sin_autenticar_devuelve_401(authapi: Api) -> None:
    """El historial sigue protegido aunque no incluya datos de contraparte."""
    client, dsns = authapi
    await seed_uploader(dsns)

    response = await client.get(history_url(), headers={"Host": "ilex.localhost"})

    assert response.status_code == 401, response.text


async def test_historial_incluye_el_numero_de_factura_cuando_existe(authapi: Api) -> None:
    """El número de la propia factura confirmada viaja en el historial (paso 8, ajustes UI).

    No es dato de contraparte (S6.12): es el número del documento propio, igual que fecha/importes.
    """
    client, dsns = authapi
    tenant_id, user_id, company_id = await seed_uploader(dsns)
    await seed_invoice(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        confirmed_by=user_id,
        invoice_number="FE-2026-004821",
    )
    token = await token_for(client, email="ana@ilex.es")

    response = await client.get(history_url(), headers=auth(token))

    assert response.status_code == 200, response.text
    entries = response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["invoice_number"] == "FE-2026-004821"


async def test_historial_sin_numero_de_factura_no_inventa_uno(authapi: Api) -> None:
    """Si la factura confirmada no tiene número, el historial devuelve null, no lo inventa."""
    client, dsns = authapi
    tenant_id, user_id, company_id = await seed_uploader(dsns)
    await seed_invoice(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        confirmed_by=user_id,
        invoice_number=None,
    )
    token = await token_for(client, email="ana@ilex.es")

    response = await client.get(history_url(), headers=auth(token))

    assert response.status_code == 200, response.text
    entries = response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["invoice_number"] is None
