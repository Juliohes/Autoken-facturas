import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Configuración de los tests de componente (S2.4): entorno jsdom (sin navegador
// real) y setup con los matchers de @testing-library/jest-dom. Es un fichero
// aparte del `vite.config.ts` de la app para no arrastrar el plugin PWA al test.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    // Base real (S4.9): jsdom por defecto arranca en `about:blank`, sin origen. El middleware del
    // cliente API (`api/client.ts`) usa URLs relativas de verdad (`fetch('/api/v1/...')`) para
    // reconstruir peticiones tras un refresh — necesitan un origen válido para resolverse.
    environmentOptions: { jsdom: { url: 'http://localhost/' } },
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
