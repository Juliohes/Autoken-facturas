// Toggle de tema (claro/oscuro) — Bloque 1. Iconos lucide (Sun/Moon).
// Accesible: grupo con radiogroup, estado anunciado, objetivos táctiles >= 44px.
// Solo ofrece Claro/Oscuro (paso 5 del SUPERPROMPT de ajustes de UI): el modo "sistema" sigue
// existiendo en useThemeMode como valor inicial por defecto hasta que el usuario elige, pero deja
// de ser una opción seleccionable en este control.
import { Moon, Sun } from 'lucide-react'

import { useThemeMode, type ThemeMode } from './useThemeMode'

const OPTIONS: Array<{ value: Exclude<ThemeMode, 'system'>; label: string; Icon: typeof Sun }> = [
  { value: 'light', label: 'Claro', Icon: Sun },
  { value: 'dark', label: 'Oscuro', Icon: Moon },
]

/** Control de tema claro/oscuro para el shell de usuario. */
export function ThemeToggle() {
  const { mode, setMode } = useThemeMode()
  return (
    <div role="radiogroup" aria-label="Tema de la aplicación" className="tn-theme-toggle">
      {OPTIONS.map(({ value, label, Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={mode === value}
          aria-label={`Tema ${label.toLowerCase()}`}
          onClick={() => setMode(value)}
          className={`tn-theme-toggle-option${mode === value ? ' tn-theme-toggle-option-active' : ''}`}
        >
          <Icon aria-hidden="true" size={18} strokeWidth={2} />
          <span>{label}</span>
        </button>
      ))}
    </div>
  )
}
