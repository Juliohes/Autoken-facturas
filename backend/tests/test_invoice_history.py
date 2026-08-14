"""Regresiones mínimas del historial privado S6.12.

Los escenarios de corte a veinte, estados pendientes/fallidos, privacidad entre compañeros y visión
de asesoría viven en ``test_multipage_intake_history.py``. Este módulo conserva las guardas HTTP que
no dependen de una factura confirmada.
"""

from __future__ import annotations

import httpx

from tests._intake import auth, seed_uploader, token_for
from tests._invoicing import history_url

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
