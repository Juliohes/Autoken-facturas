import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Configuración de los tests de componente (S2.4): entorno jsdom (sin navegador
// real) y setup con los matchers de @testing-library/jest-dom. Es un fichero
// aparte del `vite.config.ts` de la app para no arrastrar el plugin PWA al test.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
