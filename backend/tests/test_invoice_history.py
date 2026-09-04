"""Regresiones mínimas del historial privado S6.12.

Los escenarios de corte a veinte, estados pendientes/fallidos, privacidad entre compañeros y visión
de asesoría viven en ``test_multipage_intake_history.py``. Este módulo conserva las guardas HTTP que
no dependen de una factura confirmada.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx

from tests._intake import JPEG, JPEG_CT, auth, seed_uploader, token_for
from tests._invoicing import history_url, seed_invoice
from tests._ocr import seed_uploaded_file

Api = tuple[httpx.AsyncClient, dict[str, str]]

# Misma zona que invoicing.service.HISTORY_TIMEZONE: "hoy" para los tests de periodo.
_MADRID = ZoneInfo("Europe/Madrid")


def _today() -> date:
    return datetime.now(_MADRID).date()


async def _seed_confirmed_file(
    dsns: dict[str, str],
    *,
    tenant_id: str,
    company_id: str,
    user_id: str,
    issue_date: str,
) -> str:
    """Factura confirmada con `issue_date` elegido. Devuelve el id de `uploaded_files` (el que
    expone `entries[].id` en el historial), no el id de `invoices` que devuelve `seed_invoice`."""
    file_id = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=user_id,
        content=JPEG + uuid4().bytes,
        content_type=JPEG_CT,
        status="confirmed",
    )
    await seed_invoice(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        confirmed_by=user_id,
        uploaded_file_id=file_id,
        issue_date=issue_date,
    )
    return file_id


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


async def test_historial_incluye_la_fecha_de_factura_cuando_existe(authapi: Api) -> None:
    """La fecha de la propia factura (invoice_date) viaja en el historial (bloque D, ajustes v3)."""
    client, dsns = authapi
    tenant_id, user_id, company_id = await seed_uploader(dsns)
    await seed_invoice(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        confirmed_by=user_id,
        issue_date="2026-03-15",
    )
    token = await token_for(client, email="ana@ilex.es")

    response = await client.get(history_url(), headers=auth(token))

    assert response.status_code == 200, response.text
    entries = response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["invoice_date"] == "2026-03-15"


async def test_historial_count_refleja_el_total_del_filtro_no_solo_la_pagina(authapi: Api) -> None:
    """`count` cuenta TODO lo que cumple el filtro, no solo la página devuelta (bloque D)."""
    client, dsns = authapi
    tenant_id, user_id, company_id = await seed_uploader(dsns)
    for _ in range(3):
        await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id, confirmed_by=user_id)
    token = await token_for(client, email="ana@ilex.es")

    response = await client.get(f"{history_url()}?limit=2", headers=auth(token))

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["entries"]) == 2
    assert body["count"] == 3


async def test_historial_periodo_mes_filtra_por_fecha_de_factura_no_de_subida(authapi: Api) -> None:
    """period=month solo incluye facturas cuyo invoice_date cae en el mes natural en curso."""
    client, dsns = authapi
    tenant_id, user_id, company_id = await seed_uploader(dsns)
    today = _today()
    in_month = await _seed_confirmed_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        user_id=user_id,
        issue_date=today.isoformat(),
    )
    # 45 días atrás cruza siempre a un mes anterior (ningún mes tiene más de 31 días).
    await _seed_confirmed_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        user_id=user_id,
        issue_date=(today - timedelta(days=45)).isoformat(),
    )
    token = await token_for(client, email="ana@ilex.es")

    response = await client.get(f"{history_url()}?period=month", headers=auth(token))

    assert response.status_code == 200, response.text
    body = response.json()
    assert [entry["id"] for entry in body["entries"]] == [in_month]
    assert body["count"] == 1


async def test_historial_periodo_trimestre_es_natural_no_movil(authapi: Api) -> None:
    """period=quarter usa trimestres naturales (Ene-Mar/Abr-Jun/Jul-Sep/Oct-Dic), no 90 días
    móviles."""
    client, dsns = authapi
    tenant_id, user_id, company_id = await seed_uploader(dsns)
    today = _today()
    in_quarter = await _seed_confirmed_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        user_id=user_id,
        issue_date=today.isoformat(),
    )
    # 100 días atrás cruza siempre a un trimestre anterior (ningún trimestre natural pasa 92 días).
    await _seed_confirmed_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        user_id=user_id,
        issue_date=(today - timedelta(days=100)).isoformat(),
    )
    token = await token_for(client, email="ana@ilex.es")

    response = await client.get(f"{history_url()}?period=quarter", headers=auth(token))

    assert response.status_code == 200, response.text
    body = response.json()
    assert [entry["id"] for entry in body["entries"]] == [in_quarter]
    assert body["count"] == 1


async def test_historial_periodo_anio_en_curso(authapi: Api) -> None:
    """period=year solo incluye facturas del año natural en curso."""
    client, dsns = authapi
    tenant_id, user_id, company_id = await seed_uploader(dsns)
    today = _today()
    in_year = await _seed_confirmed_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        user_id=user_id,
        issue_date=today.isoformat(),
    )
    await _seed_confirmed_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        user_id=user_id,
        issue_date=date(today.year - 1, 6, 15).isoformat(),
    )
    token = await token_for(client, email="ana@ilex.es")

    response = await client.get(f"{history_url()}?period=year", headers=auth(token))

    assert response.status_code == 200, response.text
    body = response.json()
    assert [entry["id"] for entry in body["entries"]] == [in_year]
    assert body["count"] == 1


async def test_historial_periodo_total_no_filtra(authapi: Api) -> None:
    """Sin period (o period=total), no se filtra por fecha de factura."""
    client, dsns = authapi
    tenant_id, user_id, company_id = await seed_uploader(dsns)
    today = _today()
    await seed_invoice(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        confirmed_by=user_id,
        issue_date=today.isoformat(),
    )
    await seed_invoice(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        confirmed_by=user_id,
        issue_date=date(today.year - 3, 1, 1).isoformat(),
    )
    token = await token_for(client, email="ana@ilex.es")

    response = await client.get(f"{history_url()}?period=total", headers=auth(token))

    assert response.status_code == 200, response.text
    assert response.json()["count"] == 2


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
