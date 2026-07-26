# Runbook — Rotación de la clave maestra de cifrado en reposo (S5.2 C9)

> Ver spec `docs/specs/S5.2-cifrado-por-tenant.md` §2/§7 y `docs/adr/0018-cifrado-en-reposo-por-tenant.md`.
> Operación de mantenimiento **manual y explícita**: no hay ningún cron ni disparador automático.
> Rotar la clave maestra rota TODAS las claves por tenant a la vez (se derivan de ella), sin tocar
> cada tenant a mano.

## Cuándo rotar

- Sospecha de filtración de `DB_ENCRYPTION_MASTER_KEY` (acceso indebido al `.env` del VPS, log con
  el valor expuesto, etc.).
- Política de rotación periódica, si Julio decide adoptar una (no hay ninguna definida por defecto).

## Qué hace el script

`backend/scripts/rotate_encryption_key.py` (lógica en `backend/src/jobs/key_rotation.py`) re-cifra,
tenant a tenant, todo lo que vive cifrado con la clave vieja:

- `companies.cif`/`name` (+ `cif_blind_index`)
- `counterparties.cif`/`name` (+ `cif_blind_index`)
- `invoices.counterparty_tax_id`/`counterparty_name` (+ `counterparty_tax_id_blind_index`)
- `ocr_extractions.counterparty_tax_id`/`counterparty_name`
- `invoice_edits.old_value`/`new_value` de los campos sensibles (`counterparty_tax_id`,
  `counterparty_name`)

Cada tenant se rota en **su propia transacción**: si el proceso se interrumpe a mitad, ningún tenant
queda con una mezcla de clave vieja/nueva. Es **reanudable**: relanzar el mismo comando detecta los
tenants ya rotados (prueba de descifrado con la clave nueva, contra una fila de CADA tabla cifrada)
y los salta.

## ⚠️ Requiere parar la app durante la rotación (hallazgo de auditoría, obligatorio)

La rotación bloquea las filas que va leyendo (`SELECT ... FOR UPDATE`) mientras dura su propia
transacción, pero **no** puede proteger una fila que la app inserte DESPUÉS de que la rotación ya
leyó esa tabla de ese tenant y ANTES de que confirme su transacción: esa fila quedaría cifrada con
la clave vieja, y una vez descartada la clave vieja (paso 5) sería **indescifrable para siempre**,
sin ningún error visible hasta que alguien intente leerla. Por eso, a diferencia de lo que se pensó
al escribir la primera versión de este runbook, **la app NO puede seguir sirviendo tráfico de
escritura mientras el script corre**:

1. Poner la app en mantenimiento (o pararla) antes del paso 2 — no hace falta parar Postgres, solo
   el tráfico de la aplicación que pueda escribir `companies`/`counterparties`/`invoices`/
   `ocr_extractions`/`invoice_edits`.
2. Ejecutar el script (pasos 1-2 de abajo) con la app parada.
3. Reiniciar la app YA con la clave nueva en el `.env` (pasos 3-4) antes de reabrir el tráfico.

Para una sola VPS con el volumen actual del proyecto, esta ventana es corta (segundos a minutos,
según el volumen de datos); es preferible a arriesgar una pérdida de dato permanente e indetectable.

## Pasos

1. **Generar la clave nueva** (32+ bytes aleatorios, igual que se generó la clave maestra original):
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. **Parar la app** (ver aviso de arriba) y **ejecutar el script** desde `backend/`, con el venv
   activado y `DATABASE_URL` apuntando a la BD real (el script usa la misma configuración que la
   app: lee `DB_ENCRYPTION_MASTER_KEY` vigente como clave "vieja" automáticamente):
   ```bash
   DB_ENCRYPTION_MASTER_KEY_NEW="<clave nueva>" python scripts/rotate_encryption_key.py
   ```
   Revisar el resumen impreso: `N tenants, M rotados ahora, K ya estaban rotados, J sin datos`. Si
   hay fallidos (el script lo indica y sale con código 1), relanzar el mismo comando — los tenants
   ya rotados se saltan, solo se reintentan los que fallaron.
3. **Actualizar el secreto en el VPS**: cambiar `DB_ENCRYPTION_MASTER_KEY` en el `.env` real por la
   clave nueva (mismo mecanismo que el resto de secretos, §9.1 `CLAUDE.md`). **No borrar la clave
   vieja todavía** — consérvala hasta el paso 5, por si hace falta reintentar algo.
4. **Reiniciar la app** (todos los workers/procesos que lean `DB_ENCRYPTION_MASTER_KEY`) y **reabrir
   el tráfico**: sin reiniciar, la app sigue usando la clave vieja en memoria y dejará de poder leer
   los datos ya rotados.
5. **Verificar**: comprobar que el panel/las pantallas que muestran CIF/nombre de empresas y
   contrapartes siguen funcionando con normalidad (login real, ver una factura, el panel de
   facturas). Si todo va bien, ya se puede descartar la clave vieja.

## Notas de seguridad

- La clave nueva **nunca** se guarda en Postgres, ni en el script, ni en logs: solo vive en el
  parámetro/env var de la ejecución y, tras el paso 3, en el `.env` del VPS.
- El script no imprime ninguna clave en su salida (solo el resumen numérico).
- Un fallo de un tenant concreto (p. ej. una conexión caída a mitad) se registra
  (`key_rotation.tenant_failed` en los logs estructurados) y no aborta el resto: los demás tenants
  se rotan igualmente.
