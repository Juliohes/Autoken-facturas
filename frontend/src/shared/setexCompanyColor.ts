// Color determinista por nombre de empresa (HIPERDOC-FRONTEND-USUARIO-v1-setex1.md §03): la misma
// empresa recibe siempre el mismo color, de una paleta de 8 pares claro/oscuro. Portado literal
// del algoritmo original (experimento 2026-08-01, rama experiment/setex-user-ui-v1).
const PALETTE: Array<[string, string]> = [
  ['#4299e1', '#2b6cb0'], // azul
  ['#48bb78', '#276749'], // verde
  ['#ed8936', '#c05621'], // naranja
  ['#9f7aea', '#6b46c1'], // morado
  ['#38b2ac', '#285e61'], // teal
  ['#e53e3e', '#9b2c2c'], // rojo
  ['#d69e2e', '#975a16'], // ámbar
  ['#667eea', '#434190'], // índigo
]

export function setexCompanyColor(name: string): { light: string; dark: string } {
  let h = 0
  for (let i = 0; i < name.length; i++) h = ((h << 5) - h + name.charCodeAt(i)) | 0
  const [light, dark] = PALETTE[Math.abs(h) % PALETTE.length]
  return { light, dark }
}
