# ADR-0017: `reporting` como contexto de solo lectura (CQRS-light)

- **Estado**: aceptado
- **Fecha**: 2026-07-22
- **Decisores**: Julio (+ Claude Code)

## Contexto

El panel de facturas de la asesoría (S3.1) necesita listar `invoices` filtradas (fecha, proveedor/CIF,
usuario, estado del CIF), ordenadas y paginadas, con sus tramos de IVA (`invoice_tax_lines`) y la fecha de
subida del fichero (`uploaded_files.created_at`). Ninguna de esas tres tablas la posee el contexto
`reporting`: `invoices`/`invoice_tax_lines` son de `invoicing` (S2.5), `uploaded_files` es de
`invoice_intake` (S2.1).

El patrón que ya usa el resto del backend para cruzar contextos es llamar a las funciones públicas del
módulo dueño (p. ej. `invoicing.service._load_file` delega en `invoice_intake.service.authorize_file_access`,
S2.7). Ese patrón sirve para **coordinar escrituras y reglas de negocio** entre contextos. Para una
**lectura filtrada, ordenada y paginada con un JOIN** (el caso de `reporting`), llamar función a función
across contexts obligaría a traer TODAS las filas de cada contexto a Python y filtrar/paginar en memoria, o
a que `invoicing`/`invoice_intake` expusieran endpoints de lectura a medida de `reporting` (acoplando su
diseño a un consumidor).

Esto ya estaba anticipado en el backlog de auditoría del proyecto (`Auditoria_Autoken_Javi_22-06-2026.md`,
PAT-9): *"CQRS-light (S3): read models planos en `reporting/`, queries de solo-lectura → DTOs Pydantic. Nada
de event-sourcing ni bases separadas."*

## Decisión

`reporting` es un contexto de **solo lectura**: sus repositorios (`reporting/repository.py`) consultan
directamente por SQL las tablas de otros contextos (`invoices`, `invoice_tax_lines`, `uploaded_files`, y
desde S3.2 también `companies` y `users` para el export a Excel — ver enmienda abajo),
filtradas/ordenadas/paginadas para sus propios casos de uso (paneles, informes), sin pasar por los
repositorios de `invoicing`/`invoice_intake`/`companies`/`identity`. A cambio, `reporting`:

- **Nunca escribe** en ninguna tabla que no posea (ni `INSERT`/`UPDATE`/`DELETE`); el guardarraíl es
  disciplina de código, reforzado por revisión (auditoría 3 lentes) en cada tarea de `reporting`.
- Traduce las filas crudas a un **contrato propio del servicio** (p. ej. `reporting.service.InvoiceItem`),
  nunca reexporta el dataclass del repositorio hasta el router (mismo criterio que el resto del backend,
  p. ej. `invoicing.service.HistoryItem`, S2.6).
- Sigue bajo la **RLS de dos niveles** (ADR-0001): la sesión ya llega con `app.tenant_id`/`app.company_id`
  fijados; ninguna consulta de `reporting` pasa esos valores por parámetro. La RLS actúa a nivel de tabla en
  Postgres, con independencia de qué módulo Python emite el `SELECT`.
- No es event-sourcing ni una base de lectura separada: son "read models planos", SQL directo contra las
  mismas tablas transaccionales, sin infraestructura nueva (Fowler, *CQRS*: "para saber dónde parar").

## Alternativas consideradas

- **Reutilizar los repositorios de `invoicing`/`invoice_intake` función a función**: descartado para este
  caso de uso. Sirve para coordinar una operación puntual (una fila, una autorización), no para un listado
  filtrado/ordenado/paginado con JOIN: montarlo así habría significado traer todas las facturas a Python y
  paginar en memoria, o forzar a `invoicing` a exponer una API de consulta genérica que no necesita para su
  propio dominio (acoplamiento inverso).
- **Vistas SQL o proyecciones materializadas**: descartado por prematuro; el volumen actual no lo justifica
  y añade una pieza de infraestructura (refresco, consistencia) sin necesidad demostrada.

## Consecuencias

- **Positivas**: consultas de listado eficientes (un `SELECT`+`JOIN` con `LIMIT`, no N llamadas a otros
  contextos); `reporting` puede evolucionar sus vistas de lectura sin tocar `invoicing`/`invoice_intake`.
- **Negativas**: el esquema de `invoices`/`invoice_tax_lines` queda referenciado en SQL crudo en más de un
  sitio (el ORM de `invoicing`, protegido por el guard `alembic check` de CI, y ahora `reporting`); una
  migración futura que renombre/quite una columna de esas tablas debe revisar también
  `reporting/repository.py` (no hay guard automático para esto, a diferencia del ORM). Mitigación: los tests
  de `reporting` cubren todos los campos de cada fila, así que un desajuste rompe tests, no produce datos
  corruptos en silencio.
- Todo nuevo contexto de lectura agregada (futuros informes, export) que necesite cruzar tablas de varios
  contextos sigue este mismo patrón, no el de llamar función a función.

## Enmienda (2026-07-22, S3.2): export a Excel amplía el conjunto de tablas leídas

El export a Excel del panel (S3.2, `reporting.repository.list_for_export`) añade `JOIN`a `companies`
(nombre de la empresa, para una fila que puede mezclar varias empresas de la asesoría) y a `users` (email de
quien confirmó, más legible en un Excel que su id). El patrón no cambia: sigue siendo solo lectura, sigue
protegido por la RLS de dos niveles propia de `companies`/`users` (independiente de la de `invoices`,
migración 0001), y sigue traduciendo a un DTO propio del servicio (`ExportItem`, nunca `ExportRow` hasta el
router). Se deja constancia aquí para que la advertencia de "Consecuencias" (una migración de esquema debe
revisar también `reporting/repository.py`) se entienda extendida a `companies.name` y `users.email`, no solo
a `invoices`/`invoice_tax_lines`/`uploaded_files`.

## Enmienda (2026-07-23, S3.4): ficha de empresas amplía el conjunto de tablas leídas a `memberships`

La ficha agregada de empresas (S3.4, `reporting.repository.list_companies`) añade una subconsulta agregada
sobre `memberships` (contador de usuarios `active` por empresa) además de `companies`, `users` e `invoices`
(ya cubiertas por la enmienda anterior). El patrón no cambia: solo lectura, RLS de dos niveles propia de
`memberships` (migración 0001, independiente de la de `invoices`), DTO propio del servicio
(`CompanySummary`, nunca `CompanyRow` hasta el router). La advertencia de "Consecuencias" (una migración de
esquema debe revisar también `reporting/repository.py`) queda extendida también a `memberships.user_id`/
`memberships.company_id`.
