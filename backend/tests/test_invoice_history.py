"""Tests de comportamiento S2.6: historial de facturas del usuario (spec docs/specs/S2.6).

Criterios C1-C6. Observable vía HTTP (cliente ASGI con `Host` de tenant) contra Postgres real,
autenticado, con `invoices` confirmadas sembradas directamente (el `confirmed_at` real lo fija el
servidor al confirmar; para probar la ventana de 7 días se siembra la fila con la fecha deseada, tal
como indica la spec §7). Fase roja: el endpoint `GET /invoices/history` aún no existe.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import structlog.testing

from invoicing import repository
from tests._invoicing import (
    auth,
    history_url,
    seed_confirmable,
    seed_invoice,
)

Api = tuple[httpx.AsyncClient, dict[str, str]]


async def test_c1_historial_lista_confirmadas_de_7_dias_mas_reciente_primero(
    authapi: Api,
) -> None:
    """C1: tres facturas confirmadas (hoy/ayer/hace 6 días) -> 200, orden confirmed_at desc."""
    client, dsns = authapi
    s = await seed_confirmable(dsns, client)
    await seed_invoice(dsns, tenant_id=s["tenant_id"], company_id=s["company_id"], days_ago=0)
    await seed_invoice(dsns, tenant_id=s["tenant_id"], company_id=s["company_id"], days_ago=1)
    await seed_invoice(dsns, tenant_id=s["tenant_id"], company_id=s["company_id"], days_ago=6)

    resp = await client.get(history_url(), headers=auth(s["token"]))

    assert resp.status_code == 200, resp.text
    entries = resp.json()["entries"]
    assert len(entries) == 3
    ago = [e["confirmed_at"] for e in entries]
    assert ago == sorted(ago, reverse=True)


async def test_c2_facturas_de_mas_de_7_dias_no_aparecen(authapi: Api) -> None:
    """C2: una factura confirmada hace 8 días no aparece; una reciente sí."""
    client, dsns = authapi
    s = await seed_confirmable(dsns, client)
    reciente = await seed_invoice(
        dsns, tenant_id=s["tenant_id"], company_id=s["company_id"], days_ago=1
    )
    await seed_invoice(dsns, tenant_id=s["tenant_id"], company_id=s["company_id"], days_ago=8)

    resp = await client.get(history_url(), headers=auth(s["token"]))

    assert resp.status_code == 200, resp.text
    ids = {e["id"] for e in resp.json()["entries"]}
    assert ids == {reciente}


async def test_c3_facturas_de_prueba_se_excluyen(authapi: Api) -> None:
    """C3: is_test=true (admin) queda fuera del historial; is_test=false sí aparece."""
    client, dsns = authapi
    s = await seed_confirmable(dsns, client)
    normal = await seed_invoice(
        dsns, tenant_id=s["tenant_id"], company_id=s["company_id"], days_ago=0, is_test=False
    )
    await seed_invoice(
        dsns, tenant_id=s["tenant_id"], company_id=s["company_id"], days_ago=0, is_test=True
    )

    resp = await client.get(history_url(), headers=auth(s["token"]))

    assert resp.status_code == 200, resp.text
    ids = {e["id"] for e in resp.json()["entries"]}
    assert ids == {normal}


async def test_c4_historial_acotado_a_la_empresa_y_tenant_del_usuario(authapi: Api) -> None:
    """C4: solo ve las facturas de su empresa; nunca las de otra empresa/tenant."""
    client, dsns = authapi
    s = await seed_confirmable(dsns, client, slug="ilex")
    mia = await seed_invoice(dsns, tenant_id=s["tenant_id"], company_id=s["company_id"], days_ago=0)

    from tests._dbtest import seed_company  # noqa: PLC0415

    otra_empresa = await seed_company(
        dsns["admin"], tenant_id=s["tenant_id"], name="E2", cif="A39031620"
    )
    await seed_invoice(dsns, tenant_id=s["tenant_id"], company_id=otra_empresa, days_ago=0)

    from tests._dbtest import seed_tenant  # noqa: PLC0415

    tid_otra = await seed_tenant(dsns["admin"], "otra-hist", "Otra Hist")
    comp_otra = await seed_company(dsns["admin"], tenant_id=tid_otra, name="EO", cif="B06183446")
    await seed_invoice(dsns, tenant_id=tid_otra, company_id=comp_otra, days_ago=0)

    resp = await client.get(history_url(), headers=auth(s["token"]))

    assert resp.status_code == 200, resp.text
    ids = {e["id"] for e in resp.json()["entries"]}
    assert ids == {mia}


async def test_c5_historial_vacio_responde_200_con_lista_vacia(authapi: Api) -> None:
    """C5: sin facturas confirmadas en los últimos 7 días -> 200 con lista vacía (no 404)."""
    client, dsns = authapi
    s = await seed_confirmable(dsns, client)

    resp = await client.get(history_url(), headers=auth(s["token"]))

    assert resp.status_code == 200, resp.text
    assert resp.json()["entries"] == []


async def test_c6_sin_autenticar_no_hay_historial(authapi: Api) -> None:
    """C6: sin token válido -> 401."""
    client, dsns = authapi
    await seed_confirmable(dsns, client)

    resp = await client.get(history_url(), headers={"Host": "ilex.localhost"})

    assert resp.status_code == 401, resp.text


async def test_c1b_borde_7_dias_inclusive(authapi: Api) -> None:
    """Caso límite (spec §5): confirmada justo en el borde de 7 días -> se incluye (inclusivo).

    Se siembra 5 minutos por dentro de los 7 días (no en el instante exacto) para probar el borde
    sin depender de la precisión de reloj entre el seed y la consulta (evita un test inestable).
    """
    client, dsns = authapi
    s = await seed_confirmable(dsns, client)
    borde_confirmed_at = datetime.now(UTC) - timedelta(days=7) + timedelta(minutes=5)
    borde = await seed_invoice(
        dsns,
        tenant_id=s["tenant_id"],
        company_id=s["company_id"],
        confirmed_at=borde_confirmed_at,
    )

    resp = await client.get(history_url(), headers=auth(s["token"]))

    assert resp.status_code == 200, resp.text
    ids = {e["id"] for e in resp.json()["entries"]}
    assert borde in ids


async def test_c5b_al_alcanzar_la_cota_defensiva_se_registra_sin_truncar_en_silencio(
    authapi: Api, monkeypatch
) -> None:
    """Caso límite (spec §5): al llegar a la cota defensiva, se registra (no se oculta el corte).

    `HISTORY_LIMIT` se rebaja a 2 (en vez de sembrar 200 facturas) para probar el mismo
    comportamiento sin una siembra desproporcionada; el resto de tests fija el 200 real.
    """
    client, dsns = authapi
    monkeypatch.setattr(repository, "HISTORY_LIMIT", 2)
    s = await seed_confirmable(dsns, client)
    for _ in range(3):
        await seed_invoice(dsns, tenant_id=s["tenant_id"], company_id=s["company_id"], days_ago=0)

    with structlog.testing.capture_logs() as logs:
        resp = await client.get(history_url(), headers=auth(s["token"]))

    assert resp.status_code == 200, resp.text
    assert len(resp.json()["entries"]) == 2  # cortado por la cota, no las 3 sembradas
    assert any(log.get("event") == "invoice_history.limit_reached" for log in logs)
