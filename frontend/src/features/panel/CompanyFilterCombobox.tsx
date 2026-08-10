// Filtro "Empresa" del panel de facturas: buscar escribiendo, no solo desplegar y hacer scroll
// por la lista (2026-08-10, a petición de Julio — con muchas empresas dadas de alta, encontrar una
// concreta en un `<select>` nativo era lento). Combobox propio (sin librería nueva): un `<input>`
// de texto filtra la lista mientras se escribe; un clic (o Enter sobre el primer resultado) fija
// el filtro real, que sigue siendo el `company_id`, no el texto escrito.
import { useEffect, useRef, useState } from 'react'

interface Option {
  id: string
  name: string
}

interface Props {
  options: Option[]
  value: string
  onChange: (companyId: string) => void
}

export function CompanyFilterCombobox({ options, value, onChange }: Props) {
  const selectedName = options.find((o) => o.id === value)?.name ?? ''
  const [query, setQuery] = useState(selectedName)
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // El filtro puede cambiar desde fuera (p. ej. "Ver facturas" de una empresa concreta, S4.9): el
  // texto visible debe reflejarlo, no solo lo que el usuario tecleó aquí.
  useEffect(() => {
    setQuery(selectedName)
  }, [selectedName])

  useEffect(() => {
    if (!open) return
    const onPointerDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
        setQuery(selectedName)
      }
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [open, selectedName])

  const normalizedQuery = query.trim().toLowerCase()
  const filtered =
    normalizedQuery === ''
      ? options
      : options.filter((o) => o.name.toLowerCase().includes(normalizedQuery))

  const select = (companyId: string, name: string) => {
    onChange(companyId)
    setQuery(name)
    setOpen(false)
  }

  return (
    <div ref={containerRef} className="relative flex flex-col text-sm text-slate-300">
      <label htmlFor="company-filter-input">Empresa</label>
      <input
        id="company-filter-input"
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        aria-controls="company-filter-options"
        autoComplete="off"
        value={query}
        placeholder="Todas"
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            setOpen(false)
            setQuery(selectedName)
          } else if (e.key === 'Enter') {
            e.preventDefault()
            if (filtered.length > 0) select(filtered[0].id, filtered[0].name)
          }
        }}
        className="rounded border border-slate-600 bg-slate-800 px-2 py-1"
      />
      {open && (
        <ul
          id="company-filter-options"
          role="listbox"
          aria-label="Empresas"
          className="absolute top-full z-20 mt-1 max-h-56 w-full min-w-max overflow-auto rounded border border-slate-600 bg-slate-800 shadow-lg"
        >
          <li>
            <button
              type="button"
              role="option"
              aria-selected={value === ''}
              onClick={() => select('', '')}
              className="block w-full px-2 py-1 text-left hover:bg-slate-700"
            >
              Todas
            </button>
          </li>
          {filtered.length === 0 ? (
            <li className="px-2 py-1 text-slate-500">Sin resultados</li>
          ) : (
            filtered.map((o) => (
              <li key={o.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={value === o.id}
                  onClick={() => select(o.id, o.name)}
                  className="block w-full px-2 py-1 text-left hover:bg-slate-700"
                >
                  {o.name}
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  )
}
