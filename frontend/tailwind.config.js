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
      },
    },
  },
  plugins: [],
}
