// Banner de error genérico para una mutación de React Query (S4.7): extraído tras la auditoría de
// S4.7, que encontró 6 bloques casi idénticos en PlatformTenants.tsx (uno por mutación desde S4.4).
// Tipado estructural mínimo (solo `isError`/`error`) para no acoplarse a los parámetros genéricos
// de `UseMutationResult`, distintos en cada hook (`TVariables` varía: `string`, `{tenantId,...}`).
export function MutationErrorBanner({
  mutation,
  fallback,
}: {
  mutation: { isError: boolean; error: unknown }
  fallback: string
}) {
  if (!mutation.isError) return null
  return (
    <p role="alert" className="text-sm text-red-400">
      {mutation.error instanceof Error ? mutation.error.message : fallback}
    </p>
  )
}
