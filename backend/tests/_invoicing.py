"""Utilidades de test para la persistencia de facturas al confirmar (S2.5, spec docs/specs/S2.5).

No es un módulo de tests (prefijo `_`): siembra de un `uploaded_file` procesado (con su
`ocr_extraction`) confirmable sin red (S2.8 vía supplier master), y helpers para el GET de revisión,
el POST de confirmación y las consultas de efecto.

Contrato que el `implementer` debe respetar (lo fija esta fase roja):
- `GET  /api/v1/uploads/{file_id}/review`  -> datos de revisión (campos + confianzas + veredicto de
  contraparte + identidad propia + avisos). Solo lectura.
- `POST /api/v1/uploads/{file_id}/confirm` (JSON) -> 201; persiste `invoices` +
  `invoice_tax_lines` + `ocr_corrections` (diff vs OCR) + snapshot en `audit_log`; alimenta el
  supplier master (S2.8); transiciona el `uploaded_file` a `confirmed`. Reverifica el CIF en server.
- Bloqueos de servidor (422): CIF de contraparte inválido/inexistente, CIF propio ausente (salvo
  admin), responsabilidad no aceptada. Descuadre -> aviso, NO bloqueo. Reconfirmar -> 409.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import asyncpg

from tests._auth import USER_PASSWORD, USER_PASSWORD_HASH, bearer, host, login
from tests._counterparty import seed_counterparty, set_cif_sources
from tests._dbtest import seed_company, seed_membership, seed_tenant, seed_user
from tests._ocr import seed_uploaded_file

OWN_CIF = "B06183446"
COUNTERPARTY_CIF = "A39031620"
INVALID_CIF = "A39031621"

DEFAULT_TAX_LINES = [{"iva_pct": "21", "base": "100.00", "cuota": "21.00"}]


def review_url(file_id: str) -> str:
    return f"/api/v1/uploads/{file_id}/review"


def confirm_url(file_id: str) -> str:
    return f"/api/v1/uploads/{file_id}/confirm"


def history_url() -> str:
    return "/api/v1/invoices/history"


def auth(token: str, hostname: str = "ilex.localhost") -> dict[str, str]:
    return {**host(hostname), **bearer(token)}


async def seed_extraction(
    dsns: dict[str, str],
    *,
    file_id: str,
    tenant_id: str,
    company_id: str,
    counterparty_tax_id: str,
    counterparty_name: str = "Prov SA",
    own_tax_id_present: bool = True,
    issue_date: str = "2026-05-10",
    total: str = "121.00",
    net: str = "100.00",
    tax: str = "21.00",
    status: str = "needs_review",
) -> None:
    """Siembra la fila `ocr_extractions` (baseline del OCR para el diff de correcciones)."""
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "INSERT INTO ocr_extractions (id, tenant_id, company_id, uploaded_file_id, issue_date, "
            "total_amount, net_amount, tax_amount, tax_lines, counterparty_tax_id, "
            "counterparty_name, "
            "own_tax_id_present, confidences, validations, engine, model, raw, status) VALUES "
            "($1,$2,$3,$4,$5::date,$6::numeric,$7::numeric,$8::numeric,$9::jsonb,$10,$11,$12,"
            "'{}'::jsonb,'{}'::jsonb,'fake','fake-1','{}'::jsonb,$13)",
            str(uuid4()),
            tenant_id,
            company_id,
            file_id,
            date.fromisoformat(issue_date),
            total,
            net,
            tax,
            json.dumps([{"base": net, "rate": "21", "cuota": tax}]),
            counterparty_tax_id,
            counterparty_name,
            own_tax_id_present,
            status,
        )
    finally:
        await conn.close()


async def seed_confirmable(
    dsns: dict[str, str],
    client,
    *,
    slug: str = "ilex",
    email: str = "ana@ilex.es",
    role: str = "user",
    own_cif: str = OWN_CIF,
    counterparty_cif: str = COUNTERPARTY_CIF,
    counterparty_name: str = "Prov SA",
    own_present: bool = True,
    seed_master: bool = True,
    file_status: str = "needs_review",
) -> dict:
    """Siembra tenant+usuario+empresa(own_cif)+membership+uploaded_file+ocr_extraction; sin red.

    Devuelve {tenant_id, user_id, company_id, file_id, token}. `cif_sources=["supplier_master"]`
    para que la reverificación no toque red; con `seed_master` el CIF de contraparte queda `valid`.
    """
    tenant_id = await seed_tenant(dsns["admin"], slug, f"{slug.upper()} Asesoría")
    await set_cif_sources(dsns, tenant_id=tenant_id, sources=["supplier_master"])
    user_id = await seed_user(
        dsns["admin"], tenant_id=tenant_id, email=email, role=role, password_hash=USER_PASSWORD_HASH
    )
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Mi Empresa", cif=own_cif
    )
    if role == "user":
        await seed_membership(
            dsns["admin"], user_id=user_id, company_id=company_id, tenant_id=tenant_id
        )
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=user_id, status=file_status
    )
    await seed_extraction(
        dsns,
        file_id=file_id,
        tenant_id=tenant_id,
        company_id=company_id,
        counterparty_tax_id=counterparty_cif,
        counterparty_name=counterparty_name,
        own_tax_id_present=own_present,
    )
    if seed_master:
        await seed_counterparty(
            dsns, tenant_id=tenant_id, cif=counterparty_cif, name="Proveedor SA"
        )
    resp = await login(client, f"{slug}.localhost", email, USER_PASSWORD)
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "company_id": company_id,
        "file_id": file_id,
        "token": token,
    }


def confirm_body(
    *,
    counterparty_cif: str = COUNTERPARTY_CIF,
    counterparty_name: str = "Proveedor SA",
    total: str = "121.00",
    net: str = "100.00",
    tax: str = "21.00",
    tax_lines: list | None = None,
    issue_date: str = "2026-05-10",
    direction: str = "recibida",
    responsibility_accepted: bool = True,
    is_test: bool = False,
) -> dict:
    return {
        "direction": direction,
        "issue_date": issue_date,
        "counterparty_tax_id": counterparty_cif,
        "counterparty_name": counterparty_name,
        "net_amount": net,
        "tax_amount": tax,
        "total_amount": total,
        "tax_lines": tax_lines if tax_lines is not None else DEFAULT_TAX_LINES,
        "responsibility_accepted": responsibility_accepted,
        "is_test": is_test,
    }


async def seed_invoice(
    dsns: dict[str, str],
    *,
    tenant_id: str,
    company_id: str,
    days_ago: float = 0,
    confirmed_at: datetime | None = None,
    is_test: bool = False,
    counterparty_tax_id: str = COUNTERPARTY_CIF,
    counterparty_name: str = "Proveedor SA",
    total_amount: str = "121.00",
) -> str:
    """Inserta una factura confirmada directamente (S2.6), con `confirmed_at` elegido.

    El `confirmed_at` real lo fija el servidor al confirmar (S2.5); para probar la ventana de 7 días
    del historial se siembra la fila con la fecha deseada (spec S2.6 §7), en vez de pasar por el
    endpoint `confirm`. Crea su propio usuario y `uploaded_file` (FK) para no acoplarse a otro seed.
    Devuelve el id de la factura.
    """
    when = confirmed_at or (datetime.now(UTC) - timedelta(days=days_ago))
    user_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email=f"seed-invoice-{uuid4()}@example.com",
        password_hash=USER_PASSWORD_HASH,
    )
    # Contenido único por fichero (sufijo aleatorio): el UNIQUE (company_id, sha256) de
    # `uploaded_files` chocaría si dos facturas de la misma empresa reusaran el JPEG por defecto.
    from tests._intake import JPEG, JPEG_CT  # noqa: PLC0415

    file_id = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=user_id,
        content=JPEG + uuid4().bytes,
        content_type=JPEG_CT,
        status="confirmed",
    )
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow(
            "INSERT INTO invoices "
            "(tenant_id, company_id, uploaded_file_id, direction, issue_date, "
            " counterparty_tax_id, counterparty_name, counterparty_cif_status, "
            " net_amount, tax_amount, total_amount, is_test, balance_ok, snapshot, status, "
            " confirmed_by, confirmed_at) "
            "VALUES ($1,$2,$3,'recibida',$4::date,$5,$6,'valid',$7::numeric,$8::numeric,"
            " $9::numeric,$10,true,'{}'::jsonb,'confirmed',$11,$12) "
            "RETURNING id",
            tenant_id,
            company_id,
            file_id,
            date(2026, 5, 10),
            counterparty_tax_id,
            counterparty_name,
            "100.00",
            "21.00",
            total_amount,
            is_test,
            user_id,
            when,
        )
        return str(row["id"])
    finally:
        await conn.close()


# --- Consultas de efecto (superusuario) ----------------------------------------------------------
async def fetch_invoice(dsns: dict[str, str], *, file_id: str) -> dict | None:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow("SELECT * FROM invoices WHERE uploaded_file_id = $1", file_id)
        return dict(row) if row is not None else None
    finally:
        await conn.close()


async def count_invoices(dsns: dict[str, str], *, file_id: str) -> int:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        return int(
            await conn.fetchval(
                "SELECT count(*) FROM invoices WHERE uploaded_file_id = $1", file_id
            )
        )
    finally:
        await conn.close()


async def count_tax_lines(dsns: dict[str, str], *, invoice_id: str) -> int:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        return int(
            await conn.fetchval(
                "SELECT count(*) FROM invoice_tax_lines WHERE invoice_id = $1", invoice_id
            )
        )
    finally:
        await conn.close()


async def fetch_corrections(dsns: dict[str, str], *, invoice_id: str) -> list[dict]:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        rows = await conn.fetch(
            "SELECT field, ai_value, human_value FROM ocr_corrections WHERE invoice_id = $1",
            invoice_id,
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def audit_count(dsns: dict[str, str], *, action: str, entity_id: str) -> int:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        return int(
            await conn.fetchval(
                "SELECT count(*) FROM audit_log WHERE action = $1 AND entity_id = $2",
                action,
                entity_id,
            )
        )
    finally:
        await conn.close()


async def counterparty_exists(dsns: dict[str, str], *, tenant_id: str, cif: str) -> bool:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        return bool(
            await conn.fetchval(
                "SELECT 1 FROM counterparties WHERE tenant_id = $1 AND cif = $2", tenant_id, cif
            )
        )
    finally:
        await conn.close()
