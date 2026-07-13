// Extiende `expect` de vitest con los matchers de jest-dom (toBeInTheDocument,
// toBeDisabled, toHaveTextContent...) y hace su augmentación de tipos visible al
// typecheck. Se carga en cada fichero de test vía `setupFiles`.
import '@testing-library/jest-dom/vitest'
