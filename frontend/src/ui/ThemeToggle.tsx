// Toggle de tema (claro/oscuro/sistema) — Bloque 1. Iconos lucide (Sun/Moon/Monitor).
// Accesible: grupo con radiogroup, estado anunciado, objetivos táctiles >= 44px.
import { Monitor, Moon, Sun } from 'lucide-react'

import { useThemeMode, type ThemeMode } from './useThemeMode'

const OPTIONS: Array<{ value: ThemeMode; label: string; Icon: typeof Sun }> = [
  { value: 'light', label: 'Claro', Icon: Sun },
  { value: 'dark', label: 'Oscuro', Icon: Moon },
  { value: 'system', label: 'Sistema', Icon: Monitor },
]

/** Control de tema claro/oscuro/sistema para el shell de usuario. */
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
