# Spec: BP-5 `log_level` inválido falla ruidoso (fail-loud), no en silencio

> Spec-Driven Domain. Esta spec es la **fuente única** que alimenta los tests (TDD) y las auditorías.
> Si algo no está aquí, no se implementa. Aprobada por Julio antes de escribir tests.

- **ID / tarea:** BP-5 (hallazgo de `Auditoria_Autoken_Javi_22-06-2026.md`)
- **Contexto (módulo):** platform/infra (`backend/src/shared/config.py`, `backend/src/shared/logging.py`)
- **ADR relacionados:** — (validación de configuración con Pydantic; *fail-loud design*)
- **Estado:** aprobada por Julio (2026-06-30)

## 1. Problema y valor de dominio
`configure_logging` resolvía el nivel con `getattr(logging, log_level.upper(), logging.INFO)`: si el valor de
configuración no es un nivel real (p. ej. un typo `"warn"`, `"verbose"`, `"trace"`), **cae a `INFO` en
silencio**. Y `log_level` era un `str` libre en `Settings`, así que el valor malo ni se detectaba al arrancar.

Resultado: un error de configuración (querer `debug` y escribir mal el nivel) pasa desapercibido; el operador
cree que tiene un nivel y tiene otro. Los fallos silenciosos de configuración son deuda oculta. El valor de
BP-5 es que un nivel inválido **se detecte al arrancar y falle ruidoso**, en vez de degradar la observabilidad
sin avisar.

## 2. Lenguaje ubicuo
- **Nivel de log válido**: uno de `debug`, `info`, `warning`, `error`, `critical` (los de la librería estándar).
- **Fail-loud**: ante una configuración inválida, parar con un error claro al arrancar, en vez de continuar con
  un valor de reserva silencioso.

## 3. Comportamientos (criterios de aceptación)

### C1 — Un `log_level` inválido hace fallar el arranque (no se traga)  *(el bug de BP-5)*
- **Given** una configuración con `log_level` que no es un nivel real (p. ej. `"warn"`, `"verbose"`, `""`)
- **When** se construye la configuración de la aplicación (`Settings`, lo que ocurre al arrancar)
- **Then** se lanza un error de validación que **nombra** `log_level`; el arranque no continúa con `INFO` por
  defrás de forma silenciosa

### C2 — Un nivel válido se acepta en cualquier caja (mayúsculas/minúsculas)
- **Given** `log_level` igual a `"warning"`, `"WARNING"` o `"Warning"`
- **When** se construye la configuración
- **Then** es válido y queda normalizado al nivel correspondiente (la validez la decide el conjunto de niveles,
  no la caja); no se rompe el `LOG_LEVEL=info` actual del `.env`

### C3 — `configure_logging` aplica el nivel configurado y no enmascara un nivel inválido
- **Given** un nivel válido
- **When** se llama a `configure_logging`
- **Then** el logging queda configurado a ese nivel; si (por programación) se le pasara un nivel inválido,
  falla ruidoso en vez de caer a `INFO` en silencio (se elimina el valor de reserva silencioso de `:17`)

## 4. Invariantes y reglas de negocio
- **Fail-loud de configuración:** un valor de configuración inválido para `log_level` detiene el arranque con
  un error claro; nunca se degrada a un valor por defecto sin avisar.
- **Conjunto cerrado de niveles:** `log_level` solo admite los cinco niveles estándar; cualquier otro es error.
- **Tolerante a la caja:** la caja del texto no afecta a la validez (`info`/`INFO` valen igual); lo que decide
  es el nivel, no cómo se escriba.
- **Sin fallback silencioso en logging:** `configure_logging` deja de resolver el nivel con un valor de reserva
  por defecto; un nivel inesperado falla en vez de enmascararse.

## 5. Casos límite y errores
- `"info"` (valor actual del `.env`) y su default → válido, sin cambios para el operador.
- `"WARNING"` / `"Warning"` → válido (normalizado).
- `"warn"`, `"verbose"`, `"trace"`, `""`, `"123"` → error de validación al construir `Settings`.

## 6. Fuera de alcance (no-objetivos)
- Cambiar el formato de los logs, los procesadores de structlog o el destino (stdout/JSON): no se tocan.
- Añadir niveles personalizados más allá de los cinco estándar.
- Validación de otros campos de `Settings` (p. ej. `database_url`): otra tarea si surge.

## 7. Notas de verificación
- Tests nuevos en `backend/tests/test_config.py` (no existían tests de config):
  - C1: `Settings(log_level="warn")` (y otros inválidos, parametrizados) lanza `ValidationError` mencionando
    `log_level`.
  - C2: `Settings(log_level="WARNING")` es válido y normaliza al nivel esperado.
- **Diseño elegido:**
  - `LogLevel(StrEnum)` con los cinco niveles en minúsculas en `shared/config.py`.
  - `Settings.log_level: LogLevel = LogLevel.INFO` + `field_validator(mode="before")` que pasa a minúsculas las
    cadenas (tolerancia de caja); un valor fuera del enum produce `ValidationError` (fail-loud al arrancar).
  - `configure_logging(log_level: LogLevel)`: resuelve el nivel sin valor de reserva silencioso
    (`getattr(logging, log_level.upper())`, que ya nunca falla para un `LogLevel` válido).
