"""Tests de comportamiento S4.8: panel del ranking multi-modelo, extremo a extremo por HTTP
(spec docs/specs/S4.8-panel-ranking-multimodelo.md, criterios C10/C11).

Las entradas de ranking se siembran directamente en `ocr_ranking_entries` (superusuario), tal y
como recomienda la spec §7, en vez de invocar motores reales: lo que se prueba aquí es la
agregación (`ocr_ranking_summary()`, función `SECURITY DEFINER`) y el guard HTTP, no el pipeline de
extracción (ya cubierto en `test_ocr_ranking.py`).
"""

from __future__ import annotations

import httpx

from tests._auth import (
    PLATFORM_PASSWORD,
    PLATFORM_PASSWORD_HASH,
    TOTP_SECRET,
    USER_PASSWORD,
    USER_PASSWORD_HASH,
    bearer,
    host,
    login,
    totp_now,
)
from tests._dbtest import seed_company, seed_tenant, seed_user
from tests._ocr import OWN_CIF, seed_ranking_entry, seed_uploaded_file

Api = tuple[httpx.AsyncClient, dict[str, str]]

URL = "/api/v1/platform/ocr-ranking"


async def _login_platform_admin(
    client: httpx.AsyncClient, dsns: dict[str, str], *, is_admin_tech: bool, email: str
) -> str:
    await seed_user(
        dsns["admin"],
        tenant_id=None,
        email=email,
        role="platform_admin",
        password_hash=PLATFORM_PASSWORD_HASH,
        totp_secret=TOTP_SECRET,
        is_admin_tech=is_admin_tech,
    )
    resp = await login(client, "panel.localhost", email, PLATFORM_PASSWORD, totp_code=totp_now())
    assert resp.status_code == 200, resp.text
    token: str = resp.json()["access_token"]
    return token


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


async def test_c10_platform_admin_sin_flag_recibe_403(authapi: Api) -> None:
    """C10: un `platform_admin` sin `is_admin_tech` no puede leer el panel."""
    client, dsns = authapi
    token = await _login_platform_admin(
        client, dsns, is_admin_tech=False, email="alberto@autoken.es"
    )

    resp = await client.get(URL, headers={**host("panel.localhost"), **bearer(token)})

    assert resp.status_code == 403


async def test_c10_tenant_admin_y_user_nunca_pueden(authapi: Api) -> None:
    """C10: un `tenant_admin`/`user` reciben 403 directamente, igual que el resto de
    `platform_admin`."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")

    for role in ("tenant_admin", "user"):
        email = f"{role}@ilex.es"
        await seed_user(
            dsns["admin"], tenant_id=tid, email=email, role=role, password_hash=USER_PASSWORD_HASH
        )
        resp = await login(client, "ilex.localhost", email, USER_PASSWORD)
        token = resp.json()["access_token"]
        headers = {**host("ilex.localhost"), **bearer(token)}
        get_resp = await client.get(URL, headers=headers)
        assert get_resp.status_code == 403, f"{role}: {get_resp.status_code}"


async def test_c11_admin_tech_ve_el_ranking_agregado_por_motor(authapi: Api) -> None:
    """C11: agrega por motor a través de todos los tenants: facturas leídas, media, primer puesto
    (empate a puntuación máxima cuenta para AMBOS motores, sin desempate arbitrario)."""
    client, dsns = authapi
    tenant_a, company_a, file_a1 = await _seed_file(dsns, slug="rkp-a")
    file_a2 = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_a,
        company_id=company_a,
        uploaded_by=await seed_user(
            dsns["admin"], tenant_id=tenant_a, email="ana2@rkp-a.es", role="user"
        ),
        content=b"otro contenido de factura para no chocar con el UNIQUE (company_id, sha256)",
    )
    tenant_b, company_b, file_b1 = await _seed_file(dsns, slug="rkp-b")

    # Factura 1 (tenant A): empate a 5 entre gemini-3-flash y claude-vertex -> ambos primer puesto.
    await seed_ranking_entry(
        dsns,
        tenant_id=tenant_a,
        company_id=company_a,
        uploaded_file_id=file_a1,
        engine="gemini-3-flash",
        score=5,
    )
    await seed_ranking_entry(
        dsns,
        tenant_id=tenant_a,
        company_id=company_a,
        uploaded_file_id=file_a1,
        engine="claude-vertex",
        score=5,
    )
    # Factura 2 (tenant A): gemini-3-flash gana en solitario.
    await seed_ranking_entry(
        dsns,
        tenant_id=tenant_a,
        company_id=company_a,
        uploaded_file_id=file_a2,
        engine="gemini-3-flash",
        score=4,
    )
    await seed_ranking_entry(
        dsns,
        tenant_id=tenant_a,
        company_id=company_a,
        uploaded_file_id=file_a2,
        engine="claude-vertex",
        score=1,
    )
    # Factura 3 (tenant B, OTRO tenant): claude-vertex gana; comprueba que el agregado SÍ cruza
    # tenants (a diferencia de una consulta normal bajo RLS).
    await seed_ranking_entry(
        dsns,
        tenant_id=tenant_b,
        company_id=company_b,
        uploaded_file_id=file_b1,
        engine="claude-vertex",
        score=5,
    )

    token = await _login_platform_admin(client, dsns, is_admin_tech=True, email="julio@autoken.es")

    resp = await client.get(URL, headers={**host("panel.localhost"), **bearer(token)})

    assert resp.status_code == 200, resp.text
    by_engine = {row["engine"]: row for row in resp.json()}

    flash = by_engine["gemini-3-flash"]
    assert flash["invoices_read"] == 2
    assert flash["average_score"] == 4.5  # (5 + 4) / 2
    assert flash["first_place_count"] == 2  # gana sola en f2, empata en f1

    claude = by_engine["claude-vertex"]
    assert claude["invoices_read"] == 3  # f1 (tenant A) + f2 (tenant A) + f3 (tenant B)
    assert claude["average_score"] == (5 + 1 + 5) / 3
    assert claude["first_place_count"] == 2  # empata en f1, gana sola en f3 (de OTRO tenant)
