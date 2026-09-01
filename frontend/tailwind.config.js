/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      // El theming POR ASESORÍA (colores por tenant vía variables CSS, `--color-primary`/
      // `--color-secondary`) se implementó en S4.2, pero solo se aplicó en `App.tsx`/`index.html`
      // (S4.2 §decisión: "retocar las pantallas ya construidas... queda para la tarea de
      // app-shell", deuda que se va reduciendo desde la base común). Las pantallas siguen usando
      // `slate`/`emerald` de Tailwind; `emerald-600` ya pasa por el token dinámico del tenant.
      //
       // La gama clara se aplica desde los tokens compartidos para conservar intacta la estructura
       // de las pantallas. `emerald-600` sigue apuntando al color principal del tenant mediante una
       // variable CSS, así el branding dinámico no se pierde.
      colors: {
        slate: {
          100: '#263445',
          200: '#3A4B5E',
          300: '#5B6B7C',
          400: '#7B8997',
          500: '#A5B0BA',
          600: '#C8D0D6',
          700: '#E1E4E1',
          800: '#FFFFFF',
          900: '#F7F4EE',
          950: '#021232',
        },
        emerald: {
          200: '#FFC9A8',
          400: '#FF8A47',
          500: '#FF7A3D',
          600: 'var(--color-primary)',
        },
        brand: {
          primary: 'var(--color-primary)',
          secondary: 'var(--color-secondary)',
        },
      },
    },
  },
  plugins: [],
}
