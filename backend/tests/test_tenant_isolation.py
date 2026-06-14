"""Suite anti-cruce de tenants (gate de CI bloqueante — plan §8).

PLACEHOLDER de la Fase 0: aún no hay modelo de tenants ni endpoints de datos
(llegan en el Sprint 1). Este módulo existe para que el gate de aislamiento
forme parte del CI desde el principio; se rellena en S1.7 con los casos reales:
- token del tenant A + recurso del tenant B → 403/404.
- user de empresa X + recurso de empresa Y (mismo tenant) → 403/404.
- acceso a BD sin `app.tenant_id` → 0 filas (RLS).
- URLs firmadas caducadas/manipuladas → 403.
- export de A no contiene ni un byte de B.
"""

import pytest


@pytest.mark.isolation
def test_isolation_gate_placeholder() -> None:
    """Marcador del gate de aislamiento; se sustituye por casos reales en S1.7."""
    # Mientras no exista superficie multi-tenant, el gate pasa de forma explícita.
    assert True
