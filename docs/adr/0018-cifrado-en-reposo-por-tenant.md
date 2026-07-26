# ADR-0018: Cifrado en reposo por tenant (pgcrypto + HKDF + índice ciego)

- **Estado**: aceptado
- **Fecha**: 2026-07-26
- **Decisores**: Julio (+ Claude Code)

## Contexto

Antes de S5.2, el CIF/NIF y el nombre (razón social) de cada empresa (`companies`), de cada
contraparte (`counterparties`, `invoices`, `ocr_extractions`) vivían en texto plano en Postgres.
Cualquiera con acceso de lectura a la base de datos (un volcado de backup filtrado, un acceso
indebido al servidor) veía esos datos sin ningún esfuerzo adicional. Antes de producción, estos
campos debían quedar cifrados en reposo, de forma que solo la aplicación (con la clave correcta)
pudiera leerlos — y esa clave debe poder rotarse si se sospecha que se ha filtrado.

El mapa de secretos original de `CLAUDE.md` (§9.1) mencionaba "claves Fernet por tenant" como una
opción abierta, nunca implementada. Esta ADR cierra esa decisión.

## Decisión

### Mecanismo: pgcrypto, no Fernet en la aplicación

Cifrado dentro de Postgres con `pgp_sym_encrypt`/`pgp_sym_decrypt` (extensión `pgcrypto`), no Fernet
en la capa de aplicación Python. Motivo: el cifrado/descifrado ocurre en la misma sentencia SQL que
ya lee/escribe la fila (sin una vuelta extra a Python para cifrar antes de un `INSERT` o descifrar
después de un `SELECT`), y el conjunto de `GRANT EXECUTE` sobre esas dos funciones al rol runtime
(`autoken_app`) es la única superficie nueva de permisos.

### Derivación de clave: HKDF, sin tabla de claves

Un único secreto de la aplicación, la **clave maestra** (`DB_ENCRYPTION_MASTER_KEY`, env var, mismo
patrón que `JWT_SECRET`), vive solo en el `.env` del VPS — nunca en Postgres, nunca en el repo. La
**clave por tenant** se deriva de la clave maestra + `tenant_id` con HKDF (RFC 5869,
`shared.encryption.derive_tenant_encryption_key`), recalculada en cada uso: no existe ninguna tabla
de claves que gestionar, respaldar o filtrar por separado. Cada tenant tiene una clave distinta sin
coste operativo adicional; comprometer la clave de un tenant no compromete la de otro (ni falta que
haga: la RLS ya aísla las filas, esto es defensa en profundidad, no el mecanismo primario).

### Índice ciego: solo para el CIF, nunca para el nombre

`pgp_sym_encrypt` no es determinista (IV aleatorio): dos cifrados del mismo valor dan bytes
distintos, así que no sirve para `WHERE`/`UNIQUE`/`ILIKE` directamente. Para el CIF (que sí necesita
unicidad por tenant y búsqueda exacta, ADR-0011) se añade una columna `<col>_blind_index`: un
HMAC-SHA256 determinista del CIF ya normalizado (`shared.tax_id.normalize_tax_id`), con una clave de
**indexado** derivada aparte de la de cifrado (contexto HKDF distinto,
`shared.encryption.derive_tenant_index_key`/`blind_index`) — comprometer la clave de indexado
permite comparar por igualdad, nunca descifrar.

Los **nombres NO llevan índice ciego** (decisión explícita de Julio, ver más abajo): no se pueden
buscar ni comparar por igualdad, solo descifrar tras leer una fila ya localizada por otra vía.

### Alcance "ampliado": CIF y nombre, empresa propia y contraparte

Julio, preguntado explícitamente el 2026-07-26, eligió cifrar tanto el CIF/NIF como el nombre
(razón social) — de la empresa propia del tenant (`companies`) y de sus contrapartes
(`counterparties`, `invoices.counterparty_*`, `ocr_extractions.counterparty_*`) — frente a una
opción mínima (solo CIF) o una máxima (todo el contenido de la factura: importes, fechas, líneas de
IVA). Los importes/fechas/líneas de IVA quedan **fuera** de alcance: se necesitan en claro para
ordenar/sumar/filtrar por fecha e importe en el panel y los informes (S3.1/S3.2), y no son en sí
mismos un identificador de una persona/empresa concreta de la forma en que el CIF y el nombre lo son.

### El panel de facturas pierde la búsqueda de texto libre por nombre

Antes de S5.2, `reporting.repository._build_where` hacía `ILIKE` sobre `counterparty_name` (y sobre
`counterparty_tax_id`) para el filtro combinado `q` del panel (S3.1). Un `ILIKE` sobre un valor
cifrado con IV aleatorio no puede funcionar (ni siquiera una coincidencia exacta lo haría), y un
índice ciego solo sirve para igualdad exacta, no para subcadena.

Julio decidió explícitamente **mantener el nombre cifrado de verdad y retirar la búsqueda de texto
libre por nombre**, en vez de sacrificar confidencialidad (dejar el nombre en claro solo para poder
buscarlo) o inventar un índice de nombre (n-gramas, trigramas...) que habría sido una pieza de
infraestructura nueva sin necesidad demostrada. El filtro del panel pasa a ser una búsqueda
**exacta** de CIF (vía el índice ciego), no una búsqueda parcial de nombre.

## Alternativas consideradas

- **Fernet en la aplicación** (cifrar/descifrar en Python antes de tocar Postgres): descartado.
  Obliga a cifrar antes de cada `INSERT`/`UPDATE` y descifrar después de cada `SELECT` en Python, más
  superficie de código para acertar en cada punto de escritura/lectura; pgcrypto lo resuelve en la
  misma sentencia SQL.
- **Tabla de claves por tenant** (generar y guardar una clave por tenant en Postgres o en un
  secreto aparte por tenant): descartado. Añade una tabla más que proteger/respaldar y un problema de
  huevo-y-gallina (¿con qué se cifra la tabla de claves?); la derivación HKDF da el mismo resultado
  (clave distinta por tenant) sin ese problema.
- **Índice de nombre para mantener la búsqueda parcial** (n-gramas, Levenshtein sobre un hash,
  full-text search cifrado): descartado por Julio explícitamente — cualquier índice que permita
  "encontrar por fragmento" reintroduce una vía de inferencia sobre el nombre cifrado (fuga parcial),
  y es una pieza de infraestructura nueva no justificada a esta escala.
- **KMS externo** (AWS KMS, HashiCorp Vault) para la clave maestra: descartado por ahora. La clave
  maestra vive en el `.env` del VPS como el resto de secretos del proyecto (§9.1 `CLAUDE.md`); un KMS
  dedicado es una mejora futura, no necesaria a esta escala.

## Consecuencias

- **Positivas**: el CIF/nombre de empresas y contrapartes nunca vive en texto plano en Postgres; un
  volcado de backup o un acceso de solo-lectura a la BD no expone esos datos sin la clave maestra
  (fuera de Postgres). La derivación HKDF hace la rotación de la clave maestra una operación bien
  definida (script `scripts/rotate_encryption_key.py`, `jobs.key_rotation`): rotar la maestra rota
  TODAS las claves por tenant a la vez, sin tocar cada una a mano.
- **Negativas**:
  - `companies.list_companies`/`reporting.list_companies` ya no pueden `ORDER BY name` en SQL (el
    nombre es cifrado, no determinista): `companies.repository.list_companies` ordena por `id`
    (cambio de UX documentado en su propio comentario); `reporting.repository.list_companies`
    descifra y ordena en Python (volumen pequeño por tenant, el orden alfabético sí importa ahí).
  - El panel de facturas (S3.1) pierde la búsqueda de texto libre por nombre de proveedor (ver
    decisión arriba); sustituida por un filtro exacto de CIF.
  - Cada repositorio que toca una columna cifrada necesita recibir la clave del tenant ya calculada
    (nunca la deriva por su cuenta, para no esparcir `derive_tenant_encryption_key` por todo el
    código): el patrón de referencia es `companies.repository`/`companies.service`
    (`tenant_encryption_key`, `cif_blind_index`), replicado en `counterparty`, `invoicing`, `ocr`,
    `reporting` y el export de `platform_admin`.
  - `invoice_edits.old_value`/`new_value` (auditoría de ediciones, S3.3) cifran condicionalmente solo
    cuando el campo editado es sensible (`invoicing.repository.SENSITIVE_EDIT_FIELDS`): al ser
    columnas `TEXT` genéricas (comparten espacio con ediciones de importe/fecha, que siguen en
    claro), el cifrado se codifica en base64 dentro de la misma columna
    (`encode(pgp_sym_encrypt(...), 'base64')`) en vez de una columna `bytea` nueva.
  - `cif_lookups` (caché global de verificación externa, ADR-0011) queda **fuera de alcance**
    a propósito: es una tabla deliberadamente sin RLS de tenant (dato público de un registro
    oficial, compartido entre tenants), no encaja en un modelo de "clave por tenant".
  - **Hallazgo de auditoría, no detectado en la investigación previa a esta tarea**:
    `ocr_comparison_runs.original_reading`/`enhanced_reading` y `ocr_ranking_entries.reading`
    (S2.9/S2.10/S4.8) guardan una foto JSONB de cada lectura del experimento
    (`ocr.scoring.serialize_reading`), incluido el CIF/nombre de contraparte **en claro** — fuera
    del inventario cifrado de esta ADR. Mitigado por estar el experimento apagado por defecto
    (`platform_settings.ocr_experiment_enabled`, S4.10); documentado como decisión pendiente de
    Julio (spec S5.2 §6) antes de activarlo en producción, no como omisión silenciosa.

## Rotación de la clave maestra

`scripts/rotate_encryption_key.py` (lógica en `jobs.key_rotation.rotate_all_tenants`) re-cifra todo
el histórico con una clave maestra nueva, tenant a tenant, cada uno en su propia transacción
(atómico: un tenant queda del todo rotado o del todo con la clave vieja, nunca a medias), bloqueando
las filas leídas (`SELECT ... FOR UPDATE`) mientras dura esa transacción. Reanudable: si el proceso
se interrumpe, relanzar el mismo comando detecta qué tenants ya están cifrados con la clave nueva
(prueba de descifrado contra una fila de CADA tabla cifrada, no solo una) y los salta, sin fichero de
progreso aparte. Tras una rotación con éxito, el operador actualiza `DB_ENCRYPTION_MASTER_KEY` en el
`.env` del VPS y reinicia la app — la clave vieja deja de descifrar nada en cuanto termina el script,
así que debe conservarse hasta confirmar el reinicio, por si hace falta reintentar un tenant que
falló.

**Hallazgo de auditoría (2026-07-26)**: el bloqueo de filas por sí solo no protege una fila que la
app inserte con la clave vieja DESPUÉS de que la rotación ya leyó esa tabla y ANTES de comitear —
quedaría indescifrable en cuanto se descarte la clave vieja, sin ningún error visible hasta que se
intente leer. El runbook (`docs/runbooks/rotacion-clave-cifrado.md`) exige por eso una ventana sin
tráfico de escritura (parar la app) durante la rotación de cada tenant; no es opcional.
