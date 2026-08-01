// Logotipo literal de SETEX (HIPERDOC §03: "es el único elemento de marca, mantenerlo idéntico").
// Experimento 2026-08-01 (rama experiment/setex-user-ui-v1): solo se usa en las pantallas del rol
// `user`, nunca en las de plataforma/asesoría.
export function SetexBadge() {
  return (
    <span className="rounded-[7px] bg-sx-badge px-2.5 py-0.5 pb-1 text-base font-black leading-tight tracking-wide">
      <span className="text-sx-orange">SE</span>
      <span className="text-white">TEX</span>
    </span>
  )
}
