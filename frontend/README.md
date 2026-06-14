# Frontend — Autoken Facturas v2

React 18 + Vite + TypeScript + Tailwind + PWA. Cliente API **autogenerado** desde el
OpenAPI del backend (openapi-typescript + openapi-fetch).

## Estado (0.5 — esqueleto)
- Vite + React + TS + Tailwind arrancando.
- PWA manifest base (vite-plugin-pwa). El manifest dinámico por tenant llega en S4.3.
- Cliente OpenAPI tipado conectado al healthcheck del backend (`useHealth`).

## Desarrollo local

```bash
npm install
npm run gen:api      # genera src/api/schema.d.ts desde openapi.json
npm run dev          # http://localhost:5173 (proxy /api -> backend :8000)
npm run typecheck
npm run lint
npm run build
```

## Cliente API autogenerado
- `openapi.json`: snapshot del esquema del backend (regenerable desde la app).
- `npm run gen:api` → `src/api/schema.d.ts` (tipos).
- `src/api/client.ts`: cliente `openapi-fetch` tipado con esos tipos.

Para refrescar el esquema cuando cambie el backend:
```bash
# desde backend/ con el venv activo:
python -c "import json,sys; sys.path.insert(0,'src'); from main import app; print(json.dumps(app.openapi(),indent=2))" > ../frontend/openapi.json
```
