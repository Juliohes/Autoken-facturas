// Ordenar una tabla pulsando la cabecera de una columna, estilo Excel (2026-08-10, a petición de
// Julio: "ordenarlas según la columna que quiera, pulsando encima de la cabecera"). Ciclo por
// columna: ascendente -> descendente -> sin ordenar (vuelve al orden original de `rows`). Los
// valores nulos van siempre al final, en cualquier dirección (mismo criterio que una hoja de
// cálculo). Puramente en memoria: no pagina ni depende de cómo se cargaron `rows`.
import { useState } from 'react'

export type SortDirection = 'asc' | 'desc'

type SortValue = string | number | null | undefined

export function useColumnSort<T, K extends string>(
  rows: T[],
  accessors: Record<K, (row: T) => SortValue>,
) {
  const [key, setKey] = useState<K | null>(null)
  const [direction, setDirection] = useState<SortDirection>('asc')

  const toggle = (nextKey: K) => {
    if (key !== nextKey) {
      setKey(nextKey)
      setDirection('asc')
    } else if (direction === 'asc') {
      setDirection('desc')
    } else {
      setKey(null)
      setDirection('asc')
    }
  }

  const sorted =
    key === null
      ? rows
      : [...rows].sort((a, b) => {
          const accessor = accessors[key]
          const av = accessor(a)
          const bv = accessor(b)
          const sign = direction === 'asc' ? 1 : -1
          if (av == null && bv == null) return 0
          if (av == null) return 1
          if (bv == null) return -1
          if (av < bv) return -sign
          if (av > bv) return sign
          return 0
        })

  return {
    sorted,
    directionFor: (col: K): SortDirection | null => (key === col ? direction : null),
    toggle,
  }
}
