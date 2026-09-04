"""Pruebas puras de las guardas de acceso del flujo de intake."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from invoice_intake import service
from tenancy.constants import Role


@pytest.mark.asyncio
async def test_tenant_admin_solo_puede_editar_su_propio_upload(monkeypatch) -> None:
    actor_id = uuid4()
    other_owner_id = uuid4()
    context = SimpleNamespace(uploaded_by=other_owner_id)

    async def visible_file(*args, **kwargs):
        return context

    monkeypatch.setattr(service, "authorize_file_access", visible_file)

    with pytest.raises(service.FileForbidden):
        await service.authorize_file_edit(
            SimpleNamespace(),
            tenant_id=uuid4(),
            file_id=uuid4(),
            actor_user_id=actor_id,
            actor_role=Role.TENANT_ADMIN,
        )

    context.uploaded_by = actor_id
    result = await service.authorize_file_edit(
        SimpleNamespace(),
        tenant_id=uuid4(),
        file_id=uuid4(),
        actor_user_id=actor_id,
        actor_role=Role.TENANT_ADMIN,
    )

    assert result is context
