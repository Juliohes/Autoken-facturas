import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// Configuración de Vite + React + PWA. El manifest ya NO lo genera este plugin (S4.3): lo sirve el
// backend por tenant en `GET /api/v1/manifest.webmanifest` (mismo branding que S4.2), enlazado a
// mano en `index.html`. `vite-plugin-pwa` sigue generando el service worker, igual que hasta ahora.
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: false,
    }),
  ],
  server: {
    // Proxy del API al backend en desarrollo (evita CORS local).
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
