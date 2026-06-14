# ADR-0001: Aislamiento multi-tenant con PostgreSQL RLS de dos niveles

- **Estado**: aceptado
- **Fecha**: 2026-06-14
- **Decisores**: Julio (+ Claude Code)
- **Relacionado**: PLAN MAESTRO §3.3, §3.4, §8

## Contexto
La plataforma es multi-asesoría (multi-tenant) y la regla de oro nº 5 exige aislamiento total entre
asesorías: una asesoría jamás debe ver datos de otra, ni un empleado de una empresa ver datos de otra
empresa del mismo tenant. El aislamiento debe ser robusto frente a errores de programación en la capa de
aplicación (no basta con filtrar en el ORM).

## Decisión
Aislamiento defensivo en la **base de datos** con **Row-Level Security (RLS) de dos niveles**:
- Jerarquía: **Plataforma → Tenant (asesoría) → Company (empresa cliente)**.
- Toda tabla de negocio lleva `tenant_id` y (cuando aplica) `company_id`, con índice compuesto que empieza
  por `tenant_id`.
- `FORCE ROW LEVEL SECURITY` en **todas** las tablas de negocio; políticas que filtran por las variables de
  sesión `app.tenant_id` y `app.company_id`, fijadas por el middleware en cada petición.
- El **usuario de BD de la app NO es owner ni superusuario** (si lo fuera, saltaría RLS).
- El JWT incluye `tenant_id`; si no coincide con el subdominio → 403.
- Gate de CI (plan §8): una query sin `app.tenant_id` devuelve **0 filas**; cruces A↔B devuelven 403/404.

## Alternativas consideradas
- **Una base de datos por tenant**: máximo aislamiento pero operación y migraciones costosas a escala de N
  asesorías; se descarta para el MVP (se puede reconsiderar para clientes muy grandes).
- **Aislamiento solo en la capa de aplicación** (filtros en el ORM): un único `WHERE` olvidado filtra datos
  entre tenants. Insuficiente como única defensa.
- **Esquema por tenant**: complica migraciones y pooling; RLS cubre el caso con menos fricción.

## Consecuencias
- (+) Aislamiento garantizado por el motor, resistente a fallos de la capa de app.
- (+) Una sola BD: migraciones y backups simples.
- (−) Disciplina obligatoria: toda tabla nueva necesita su política RLS y su test de aislamiento.
- (−) El middleware debe fijar siempre las variables de sesión; conexión de app sin privilegios elevados.
