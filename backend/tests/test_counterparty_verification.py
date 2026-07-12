"""Tests de comportamiento S2.8: verificación del CIF de contraparte (spec docs/specs/S2.8).

Criterios C1-C13. Observable llamando a `counterparty.service.verify_counterparty` contra Postgres
real, con resolvers doblados (sin red en CI). Se comprueba el `CounterpartyVerdict` y el efecto en
`counterparties` (supplier master por tenant) y `cif_lookups` (caché global). Fase roja: el módulo
`counterparty` aún no existe.
"""

from __future__ import annotations

from tests._counterparty import (
    INVALID_CIF,
    VALID_CIF,
    FakeResolver,
    confirm,
    counterparties_visible_as_tenant,
    fetch_cif_lookup,
    fetch_counterparty,
    seed_cif_lookup,
    seed_counterparty,
    set_cif_sources,
    verify,
)
from tests._dbtest import seed_tenant

Api = tuple[object, dict[str, str]]


def _aeat(**kw: object) -> FakeResolver:
    return FakeResolver(source="aeat", negative_authoritative=True, **kw)


def _vies(**kw: object) -> FakeResolver:
    return FakeResolver(source="vies", negative_authoritative=False, **kw)


async def _tenant(dsns: dict[str, str], slug: str = "ilex") -> str:
    return await seed_tenant(dsns["admin"], slug, f"{slug.upper()} Asesoría")


# --- Estructura (L1) y supplier master (L2) ------------------------------------------------------
async def test_c1_cif_estructural_invalido_bloquea_sin_red(authapi: Api) -> None:
    """C1: CIF con mód-23 KO -> invalid, sin llamar a fuentes externas ni cachear."""
    _c, dsns = authapi
    tid = await _tenant(dsns)
    aeat = _aeat(exists=True, official_name="X")

    verdict = await verify(
        dsns, tenant_id=tid, cif=INVALID_CIF, name_read="X", resolvers={"aeat": aeat}
    )

    assert verdict.status == "invalid"
    assert verdict.source == "structure"
    assert aeat.calls == []  # no se gasta cuota en basura
    assert await fetch_cif_lookup(dsns, cif=INVALID_CIF, source="aeat") is None


async def test_c2_supplier_master_resuelve_sin_red(authapi: Api) -> None:
    """C2: un CIF ya en el master del tenant -> valid por L2, sin llamar a externas."""
    _c, dsns = authapi
    tid = await _tenant(dsns)
    await seed_counterparty(dsns, tenant_id=tid, cif=VALID_CIF, name="Proveedor SA")
    aeat = _aeat(exists=True, official_name="Proveedor SA")

    verdict = await verify(
        dsns, tenant_id=tid, cif=VALID_CIF, name_read="Proveedor SA", resolvers={"aeat": aeat}
    )

    assert verdict.status == "valid"
    assert verdict.source == "supplier_master"
    assert verdict.name_match is True
    assert verdict.official_name == "Proveedor SA"
    assert aeat.calls == []


async def test_c3_supplier_master_nombre_no_coincide_avisa(authapi: Api) -> None:
    """C3: CIF en el master pero nombre leído distinto -> valid + name_match False (aviso)."""
    _c, dsns = authapi
    tid = await _tenant(dsns)
    await seed_counterparty(dsns, tenant_id=tid, cif=VALID_CIF, name="Proveedor SA")

    verdict = await verify(
        dsns, tenant_id=tid, cif=VALID_CIF, name_read="Prov Equivocada SL", resolvers={}
    )

    assert verdict.status == "valid"
    assert verdict.name_match is False
    assert verdict.official_name == "Proveedor SA"


# --- Resolución externa (L3) + caché (L4) --------------------------------------------------------
async def test_c4_aeat_confirma_par_cif_nombre(authapi: Api) -> None:
    """C4: AEAT identifica el par y coincide -> valid, source aeat; se cachea en cif_lookups."""
    _c, dsns = authapi
    tid = await _tenant(dsns)
    aeat = _aeat(exists=True, official_name="Proveedor SA", name_match=True)

    verdict = await verify(
        dsns, tenant_id=tid, cif=VALID_CIF, name_read="Proveedor SA", resolvers={"aeat": aeat}
    )

    assert verdict.status == "valid"
    assert verdict.name_match is True
    assert verdict.source == "aeat"
    row = await fetch_cif_lookup(dsns, cif=VALID_CIF, source="aeat")
    assert row is not None and row["exists"] is True


async def test_c5_aeat_nombre_no_concuerda_avisa(authapi: Api) -> None:
    """C5: AEAT dice que el CIF existe pero el nombre no concuerda -> valid + name_match False."""
    _c, dsns = authapi
    tid = await _tenant(dsns)
    aeat = _aeat(exists=True, official_name="Nombre Oficial SA", name_match=False)

    verdict = await verify(
        dsns, tenant_id=tid, cif=VALID_CIF, name_read="Otro Nombre SL", resolvers={"aeat": aeat}
    )

    assert verdict.status == "valid"
    assert verdict.name_match is False
    assert verdict.official_name == "Nombre Oficial SA"


async def test_c6_cif_inexistente_not_found_bloquea(authapi: Api) -> None:
    """C6: AEAT (autoritativa) dice que el CIF no existe -> not_found; se cachea exists False."""
    _c, dsns = authapi
    tid = await _tenant(dsns)
    aeat = _aeat(exists=False)

    verdict = await verify(
        dsns, tenant_id=tid, cif=VALID_CIF, name_read="X", resolvers={"aeat": aeat}
    )

    assert verdict.status == "not_found"
    assert verdict.source == "aeat"
    row = await fetch_cif_lookup(dsns, cif=VALID_CIF, source="aeat")
    assert row is not None and row["exists"] is False


async def test_c7a_cache_fresca_evita_la_llamada(authapi: Api) -> None:
    """C7: con la caché fresca (L4) no se vuelve a llamar al resolver."""
    _c, dsns = authapi
    tid = await _tenant(dsns)
    await seed_cif_lookup(
        dsns, cif=VALID_CIF, source="aeat", exists=True, official_name="Proveedor SA"
    )
    aeat = _aeat(exists=True, official_name="Proveedor SA")

    verdict = await verify(
        dsns, tenant_id=tid, cif=VALID_CIF, name_read="Proveedor SA", resolvers={"aeat": aeat}
    )

    assert verdict.status == "valid"
    assert aeat.calls == []  # cache hit


async def test_c7b_cache_caducada_refetcha(authapi: Api) -> None:
    """C7: con la caché caducada (TTL vencido) se vuelve a resolver."""
    _c, dsns = authapi
    tid = await _tenant(dsns)
    await seed_cif_lookup(
        dsns, cif=VALID_CIF, source="aeat", exists=True, official_name="Viejo", fresh=False
    )
    aeat = _aeat(exists=True, official_name="Proveedor SA", name_match=True)

    verdict = await verify(
        dsns, tenant_id=tid, cif=VALID_CIF, name_read="Proveedor SA", resolvers={"aeat": aeat}
    )

    assert verdict.status == "valid"
    assert len(aeat.calls) == 1  # se refetcha


async def test_c8_cache_global_entre_tenants(authapi: Api) -> None:
    """C8: la caché es global; un CIF resuelto por un tenant lo reutiliza otro (sin re-llamar)."""
    _c, dsns = authapi
    tid_ilex = await _tenant(dsns, "ilex")
    tid_otra = await _tenant(dsns, "otra")
    aeat_ilex = _aeat(exists=True, official_name="Proveedor SA", name_match=True)
    await verify(
        dsns,
        tenant_id=tid_ilex,
        cif=VALID_CIF,
        name_read="Proveedor SA",
        resolvers={"aeat": aeat_ilex},
    )

    aeat_otra = _aeat(exists=True, official_name="Proveedor SA", name_match=True)
    verdict = await verify(
        dsns,
        tenant_id=tid_otra,
        cif=VALID_CIF,
        name_read="Proveedor SA",
        resolvers={"aeat": aeat_otra},
    )

    assert verdict.status == "valid"
    assert aeat_otra.calls == []  # reutiliza la caché global de ilex


# --- Disponibilidad y feature flags --------------------------------------------------------------
async def test_c9_fuentes_caidas_unverified_no_bloquea(authapi: Api) -> None:
    """C9: fuentes externas caídas/timeout -> unverified (manual), nunca invalid/not_found."""
    _c, dsns = authapi
    tid = await _tenant(dsns)
    resolvers = {
        "aeat": _aeat(unavailable=True),
        "vies": _vies(unavailable=True),
        "borme": FakeResolver(source="borme", unavailable=True),
    }

    verdict = await verify(dsns, tenant_id=tid, cif=VALID_CIF, name_read="X", resolvers=resolvers)

    assert verdict.status == "unverified"
    assert verdict.name_match is None
    # un fallo de red no se cachea como "no existe"
    assert await fetch_cif_lookup(dsns, cif=VALID_CIF, source="aeat") is None


async def test_c10_vies_no_autoritativo_para_lo_nacional(authapi: Api) -> None:
    """C10: el negativo de VIES (no autoritativo) no invalida; manda la respuesta de AEAT."""
    _c, dsns = authapi
    tid = await _tenant(dsns)
    await set_cif_sources(dsns, tenant_id=tid, sources=["vies", "aeat"])
    vies = _vies(exists=False)
    aeat = _aeat(exists=True, official_name="Proveedor SA", name_match=True)

    verdict = await verify(
        dsns,
        tenant_id=tid,
        cif=VALID_CIF,
        name_read="Proveedor SA",
        resolvers={"vies": vies, "aeat": aeat},
    )

    assert verdict.status == "valid"
    assert verdict.source == "aeat"
    assert len(vies.calls) == 1 and len(aeat.calls) == 1


async def test_c11_feature_flags_solo_supplier_master(authapi: Api) -> None:
    """C11: tenant con solo supplier_master no llama a externas -> unverified si no está."""
    _c, dsns = authapi
    tid = await _tenant(dsns)
    await set_cif_sources(dsns, tenant_id=tid, sources=["supplier_master"])
    aeat = _aeat(exists=True, official_name="Proveedor SA")

    verdict = await verify(
        dsns, tenant_id=tid, cif=VALID_CIF, name_read="Proveedor SA", resolvers={"aeat": aeat}
    )

    assert verdict.status == "unverified"
    assert aeat.calls == []  # no habilitado


# --- Mejora continua y aislamiento ---------------------------------------------------------------
async def test_c12_confirmar_alimenta_el_master_aislado_por_tenant(authapi: Api) -> None:
    """C12: confirmar upserta el master del tenant (times_seen++); otro tenant NO lo hereda."""
    _c, dsns = authapi
    tid_ilex = await _tenant(dsns, "ilex")
    tid_otra = await _tenant(dsns, "otra")

    await confirm(dsns, tenant_id=tid_ilex, cif=VALID_CIF, name="Proveedor SA")
    await confirm(dsns, tenant_id=tid_ilex, cif=VALID_CIF, name="Proveedor SA")
    row = await fetch_counterparty(dsns, tenant_id=tid_ilex, cif=VALID_CIF)
    assert row is not None and row["times_seen"] == 2

    # En ilex acierta por L2 sin llamar a externas.
    aeat_ilex = _aeat(exists=True, official_name="Proveedor SA")
    v_ilex = await verify(
        dsns,
        tenant_id=tid_ilex,
        cif=VALID_CIF,
        name_read="Proveedor SA",
        resolvers={"aeat": aeat_ilex},
    )
    assert v_ilex.source == "supplier_master"
    assert aeat_ilex.calls == []

    # En otra NO existe ese master: debe resolver por externas.
    aeat_otra = _aeat(exists=True, official_name="Proveedor SA", name_match=True)
    v_otra = await verify(
        dsns,
        tenant_id=tid_otra,
        cif=VALID_CIF,
        name_read="Proveedor SA",
        resolvers={"aeat": aeat_otra},
    )
    assert v_otra.source == "aeat"
    assert len(aeat_otra.calls) == 1


async def test_c13_counterparties_aislado_por_tenant(authapi: Api) -> None:
    """C13: cada tenant solo ve su supplier master bajo el rol runtime (RLS por tenant)."""
    _c, dsns = authapi
    tid_ilex = await _tenant(dsns, "ilex")
    tid_otra = await _tenant(dsns, "otra")
    await seed_counterparty(dsns, tenant_id=tid_ilex, cif=VALID_CIF, name="Proveedor SA")
    await seed_counterparty(dsns, tenant_id=tid_otra, cif=VALID_CIF, name="Otro Prov SA")

    assert await counterparties_visible_as_tenant(dsns, tenant_id=tid_ilex) == 1
    assert await counterparties_visible_as_tenant(dsns, tenant_id=tid_otra) == 1
