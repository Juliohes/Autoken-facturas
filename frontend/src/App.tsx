import { BrowserRouter } from 'react-router-dom'

import { AppRoutes } from './app/AppRoutes'
import { SessionProvider } from './features/session/SessionProvider'
import { useTenantTheme } from './features/tenancy/useTenantTheme'

// Composición raíz de la app (S4.9). `useTenantTheme` sigue montado una única vez arriba del todo
// (decisión 9): el branding del tenant debe verse tanto en el login como en el resto del árbol, y
// es intencionalmente tolerante a fallos (S4.2), nunca bloquea el arranque.
export default function App() {
  const theme = useTenantTheme()

  return (
    <BrowserRouter>
      <SessionProvider>
        <AppRoutes theme={theme} />
      </SessionProvider>
    </BrowserRouter>
  )
}
