/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      // El theming POR ASESORÍA (colores por tenant vía variables CSS, `--color-primary`/
      // `--color-secondary`) se implementó en S4.2, pero solo se aplicó en `App.tsx`/`index.html`
      // (S4.2 §decisión: "retocar las pantallas ya construidas... queda para la tarea de
      // app-shell", nunca hecho — deuda conocida). Cada pantalla usa directamente las paletas
      // `slate`/`emerald` de Tailwind sin pasar por esas variables.
      //
      // Esto redefine esas DOS paletas con los colores reales de la marca Autoken (logo + web
      // corporativa, `/opt/autoken/web/styles.css`) — `slate` (fondos/texto oscuro) -> la gama
      // navy real del logo; `emerald` (acento/botón principal) -> el naranja real. Como todas las
      // pantallas ya construidas usan estos dos nombres de forma consistente (150+ usos de
      // `slate-*`, 14 de `emerald-*`, verificado con grep antes de tocar esto), cambia el aspecto
      // de TODA la app sin tener que tocar cada componente uno a uno.
      colors: {
        slate: {
          100: '#E8EDF5',
          200: '#D3DBE8',
          300: '#B7C3D8',
          400: '#7C8CA8',
          500: '#3A4A66',
          600: '#22314D',
          700: '#16233B', // navy exacto del logotipo
          800: '#101A2E',
          900: '#0B1322',
        },
        emerald: {
          200: '#FFC9A8',
          400: '#FF8A47',
          500: '#FF7A3D',
          600: '#F26522', // naranja de marca
        },
        // Paleta EXPERIMENTAL (2026-08-01, rama experiment/setex-user-ui-v1): sistema de diseño
        // de SETEX v1 (HIPERDOC-FRONTEND-USUARIO-v1-setex1.md §03), namespace `sx-*` a propósito
        // para no tocar ni una clase `slate-*`/`emerald-*` existente — cero riesgo para el resto
        // de la app (paneles de plataforma/asesoría) aunque esta rama nunca llegue a `develop`.
        // Solo se usa en las pantallas del rol `user` (captura/confirmación/historial).
        sx: {
          brand: '#667eea',
          brand2: '#764ba2',
          orange: '#FF6600',
          badge: '#2d3748',
          ink1: '#2d3748',
          ink2: '#4a5568',
          ink3: '#718096',
          faint1: '#a0aec0',
          faint2: '#cbd5e0',
          line: '#e2e8f0',
          ok: '#276749',
          okBg: '#c6f6d5',
          warn: '#975a16',
          warnBg: '#fefcbf',
          bad: '#9b2c2c',
          badBg: '#fed7d7',
          ivaBorder: '#bee3f8',
          ivaBg: '#ebf8ff',
          ivaText: '#2b6cb0',
          irpfBorder: '#fbd38d',
          irpfBg: '#fffaf0',
          irpfText: '#c05621',
          resumen: '#1a365d',
          recibidaBorder: '#4299e1',
          recibidaBg: '#ebf8ff',
          recibidaText: '#2b6cb0',
          emitidaBorder: '#48bb78',
          emitidaBg: '#f0fff4',
          emitidaText: '#276749',
          inactiveBg: '#f7fafc',
          inactiveBorder: '#e2e8f0',
          inactiveText: '#a0aec0',
        },
      },
    },
  },
  plugins: [],
}
