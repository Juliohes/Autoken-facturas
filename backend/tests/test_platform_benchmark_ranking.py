"""Tests de comportamiento S6.7 Área D (ranking por grupo de campo), spec
docs/specs/S6.7-benchmark-real-motor-variante.md, C18-C20.

Postgres real, admin-tech autenticado. Nunca dispara ninguna llamada real (C19: la agregación solo
lee `ocr_benchmark_results` ya persistida) -- verificado implícitamente por diseño, no hay ningún
extractor inyectable en este endpoint (es un `GET` de solo lectura sobre datos ya guardados).
"""

from __future__ import annotations

import httpx

from tests._dbtest import seed_company, seed_tenant, seed_user
from tests._ocr import OWN_CIF, seed_uploaded_file
from tests._ocr_benchmark import seed_benchmark_result
from tests._platform import platform_token, seed_platform_admin

Api = tuple[httpx.AsyncClient, dict[str, str]]

_RANKING_URL = "/api/v1/platform/benchmark/ranking"


def _platform_auth(token: str) -> dict[str, str]:
    return {"Host": "panel.localhost", "Authorization": f"Bearer {token}"}


async def _admin_tech_token(client: httpx.AsyncClient, dsns: dict[str, str]) -> str:
    await seed_platform_admin(dsns, is_admin_tech=True)
    return await platform_token(client)


async def _seed_file(dsns: dict[str, str], *, slug: str) -> tuple[str, str, str]:
    tenant_id = await seed_tenant(dsns["admin"], slug, f"{slug.upper()} Asesoría")
    user_id = await seed_user(
        dsns["admin"], tenant_id=tenant_id, email=f"ana@{slug}.es", role="user"
    )
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Mi Empresa", cif=OWN_CIF
    )
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=user_id
    )
    return tenant_id, company_id, file_id


def _fields(**overrides: bool | None) -> list[dict]:
    base = {
        "counterparty_tax_id": True,
        "counterparty_name": True,
        "invoice_number": True,
        "issue_date": True,
        "total_amount": True,
        "net_amount": True,
        "tax_amount": True,
    }
    base.update(overrides)
    return [{"field": f, "match": m} for f, m in base.items()]


async def test_c1_sin_admin_tech_da_403(authapi: Api) -> None:
    client, dsns = authapi
    await seed_platform_admin(dsns, is_admin_tech=False)
    token = await platform_token(client)

    resp = await client.get(_RANKING_URL, headers=_platform_auth(token))

    assert resp.status_code == 403, resp.text


async def test_c18_el_ranking_por_grupo_muestra_la_mejor_combinacion_para_cada_grupo(
    authapi: Api,
) -> None:
    """spec: C18 -- dos motores que ganan en grupos DISTINTOS deben verse los dos, no un único
    ganador global que esconda cuál acierta más en CIF/NIF y cuál en Fecha."""
    client, dsns = authapi
    tenant_id, company_id, file_a = await _seed_file(dsns, slug="rk-c18a")
    _tid2, _cid2, file_b = await _seed_file(dsns, slug="rk-c18b")

    # motor-a: acierta el CIF, falla la fecha.
    await seed_benchmark_result(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_file_id=file_a,
        variant="original",
        engine="motor-a",
        field_results=_fields(counterparty_tax_id=True, issue_date=False),
    )
    # motor-b: falla el CIF, acierta la fecha.
    await seed_benchmark_result(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_file_id=file_b,
        variant="original",
        engine="motor-b",
        field_results=_fields(counterparty_tax_id=False, issue_date=True),
    )
    token = await _admin_tech_token(client, dsns)

    resp = await client.get(_RANKING_URL, headers=_platform_auth(token))

    assert resp.status_code == 200, resp.text
    by_group = {
        (r["field_group"], r["variant"], r["engine"]): r for r in resp.json()["by_field_group"]
    }

    cif_a = by_group[("CIF/NIF", "original", "motor-a")]
    assert cif_a["aciertos"] == 1 and cif_a["comparables"] == 1
    cif_b = by_group[("CIF/NIF", "original", "motor-b")]
    assert cif_b["aciertos"] == 0 and cif_b["comparables"] == 1

    fecha_a = by_group[("Fecha", "original", "motor-a")]
    assert fecha_a["aciertos"] == 0
    fecha_b = by_group[("Fecha", "original", "motor-b")]
    assert fecha_b["aciertos"] == 1


async def test_c18_tramos_de_iva_es_su_propio_grupo_no_parte_de_importes(authapi: Api) -> None:
    """spec: C18 -- `tax_lines_matched` (columna propia, no dentro de `field_results`) forma su
    propio grupo "Tramos IVA", separado del grupo "Importes"."""
    client, dsns = authapi
    tenant_id, company_id, file_id = await _seed_file(dsns, slug="rk-c18c")
    await seed_benchmark_result(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_file_id=file_id,
        variant="original",
        engine="motor-a",
        field_results=_fields(total_amount=True, net_amount=True, tax_amount=True),
        tax_lines_matched=False,
    )
    token = await _admin_tech_token(client, dsns)

    resp = await client.get(_RANKING_URL, headers=_platform_auth(token))

    by_group = {
        (r["field_group"], r["variant"], r["engine"]): r for r in resp.json()["by_field_group"]
    }
    importes = by_group[("Importes", "original", "motor-a")]
    assert importes["aciertos"] == 3 and importes["comparables"] == 3
    tramos = by_group[("Tramos IVA", "original", "motor-a")]
    assert tramos["aciertos"] == 0 and tramos["comparables"] == 1


async def test_c19_el_ranking_no_dispara_ninguna_llamada_real_solo_lee_lo_ya_persistido(
    authapi: Api,
) -> None:
    """spec: C19 -- el endpoint es un GET puro sobre datos ya guardados, sin ningún parámetro que
    permita inyectar/disparar un motor real."""
    client, dsns = authapi
    token = await _admin_tech_token(client, dsns)

    resp = await client.get(_RANKING_URL, headers=_platform_auth(token))

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"by_field_group": [], "by_combination": []}


async def test_ratio_es_null_no_cero_cuando_el_grupo_no_tiene_ningun_dato_comparable(
    authapi: Api,
) -> None:
    """auditoría S6.7 (SOLID, hallazgo MEDIO): un grupo sin ningún dato comparable
    (`comparables == 0` -- p. ej. la verdad confirmada no tenía CIF de contraparte, spec C5, "campo
    no comparable... no puntúa a favor ni en contra") debe exponer `ratio: null`, nunca `0.0` --
    confundirlos sería lo mismo que confundir "no leído" con "leído e incorrecto". La fila en sí no
    tiene `error` (sigue contando en `by_combination` como ejecución exitosa, comparables=6 en
    total por los otros 6 campos)."""
    client, dsns = authapi
    tenant_id, company_id, file_id = await _seed_file(dsns, slug="rk-nulo")
    await seed_benchmark_result(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_file_id=file_id,
        variant="clahe",
        engine="motor-sin-cif",
        # `counterparty_tax_id` no comparable (verdad ausente): `match=None`, no True/False.
        field_results=_fields(counterparty_tax_id=None),
        tax_lines_matched=None,
        aciertos=6,
        comparables=6,
    )
    token = await _admin_tech_token(client, dsns)

    resp = await client.get(_RANKING_URL, headers=_platform_auth(token))

    assert resp.status_code == 200, resp.text
    by_group = {
        (r["field_group"], r["variant"], r["engine"]): r for r in resp.json()["by_field_group"]
    }

    cif = by_group[("CIF/NIF", "clahe", "motor-sin-cif")]
    assert cif["comparables"] == 0
    assert cif["ratio"] is None

    importes = by_group[("Importes", "clahe", "motor-sin-cif")]
    assert importes["comparables"] == 3
    assert importes["ratio"] == 1.0


async def test_c20_la_tabla_de_detalle_por_combinacion_incluye_ejecuciones_y_errores(
    authapi: Api,
) -> None:
    """spec: C20 -- por combinación (variante x motor): ratio global, ejecuciones, errores, tiempo
    medio -- sin filtrar los fallidos de las ejecuciones/errores, solo del ratio de acierto."""
    client, dsns = authapi
    tenant_id, company_id, file_a = await _seed_file(dsns, slug="rk-c20a")
    _t2, _c2, file_b = await _seed_file(dsns, slug="rk-c20b")

    await seed_benchmark_result(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_file_id=file_a,
        variant="clahe",
        engine="motor-x",
        aciertos=8,
        comparables=8,
        duration_ms=100,
    )
    await seed_benchmark_result(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_file_id=file_b,
        variant="clahe",
        engine="motor-x",
        error="timeout",
        aciertos=0,
        comparables=0,
        field_results=[],
        tax_lines_matched=None,
        duration_ms=None,
        counterparty_tax_id=None,
        counterparty_name=None,
    )
    token = await _admin_tech_token(client, dsns)

    resp = await client.get(_RANKING_URL, headers=_platform_auth(token))

    by_combo = {(r["variant"], r["engine"]): r for r in resp.json()["by_combination"]}
    row = by_combo[("clahe", "motor-x")]
    assert row["executions"] == 2
    assert row["errors"] == 1
    assert row["aciertos"] == 8
    assert row["comparables"] == 8
