// Lee el `detail` de un error de `openapi-fetch` (cuerpo `{ detail: string }` de FastAPI),
// compartido por las mutaciones de cualquier pantalla para no repetir el mismo `unknown`-narrowing.
export function errorDetail(error: unknown): string | undefined {
  if (error && typeof error === 'object' && 'detail' in error) {
    const { detail } = error as { detail: unknown }
    return typeof detail === 'string' ? detail : undefined
  }
  return undefined
}
