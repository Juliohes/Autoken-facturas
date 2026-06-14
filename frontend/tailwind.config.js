/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      // El theming por asesoría (colores por tenant vía variables CSS)
      // se implementa en el Sprint 4 (S4.2).
    },
  },
  plugins: [],
}
