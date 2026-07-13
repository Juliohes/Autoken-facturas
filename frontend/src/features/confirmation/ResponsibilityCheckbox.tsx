// Checkbox obligatorio de aceptación de responsabilidad (spec §2/§4, regla 8, C7).
interface Props {
  checked: boolean
  onChange: (checked: boolean) => void
}

export function ResponsibilityCheckbox({ checked, onChange }: Props) {
  return (
    <label className="flex items-start gap-2 text-sm text-slate-200">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-1"
      />
      <span>Acepto la responsabilidad de la veracidad de los datos que confirmo.</span>
    </label>
  )
}
