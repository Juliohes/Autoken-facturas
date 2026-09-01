// Hook de tema (claro/oscuro/sistema) — Bloque 1 del sistema de diseño.
// Escribe `data-theme` en <html> y persiste la elección en localStorage envuelto en try/catch
// (modo incógnito puede lanzar). Por defecto "sistema": sigue prefers-color-scheme del SO.
// El modo "sistema" ya no es seleccionable desde ThemeToggle (paso 5 del SUPERPROMPT de ajustes
// de UI), pero se conserva aquí como valor inicial implícito hasta que el usuario elige claro u
// oscuro explícitamente.
import { useCallback, useEffect, useState } from 'react'

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'autofactu-theme'

function readStoredMode(): ThemeMode {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    return stored === 'light' || stored === 'dark' ? stored : 'system'
  } catch {
    return 'system'
  }
}

function applyMode(mode: ThemeMode): void {
  const root = document.documentElement
  if (mode === 'system') {
    // Sin override explícito: el bloque @media (prefers-color-scheme: dark) de index.css resuelve.
    root.removeAttribute('data-theme')
    return
  }
  root.setAttribute('data-theme', mode)
}

/** Hook del toggle de tema. Devuelve el modo actual y un setter que aplica y persiste. */
export function useThemeMode(): { mode: ThemeMode; setMode: (mode: ThemeMode) => void } {
  const [mode, setModeState] = useState<ThemeMode>(() => readStoredMode())

  useEffect(() => {
    applyMode(mode)
  }, [mode])

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next)
    try {
      window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Incógnito / almacenamiento bloqueado: el tema se aplica igualmente en esta sesión.
    }
  }, [])

  return { mode, setMode }
}
