// Mensaje compartido por las 5 pantallas públicas de auth (Bloque 4): un 404 en cualquiera de sus
// endpoints significa SIEMPRE lo mismo (backend, tenancy/context.py::public_tenant_context) -- el
// subdominio por el que se entró no resuelve a ningún tenant activo (inexistente, suspendido, o un
// dominio que no es de ninguna gestoría, como la consola de plataforma). Nunca "no se encontró el
// email/token" -- eso son 401/422/429 propios de cada endpoint, con su propio mensaje.
//
// Hallazgo real (Julio, 2026-09-03): probó a registrarse desde panel-staging.autoken.es (su consola
// de plataforma, no una gestoría) y la pantalla enseñaba el "Not found" crudo del backend.
export const TENANT_NOT_FOUND_MESSAGE =
  'Este sitio no admite esta acción. Comprueba que has entrado por la dirección de tu asesoría (por ejemplo, tuasesoria.autoken.es), no por esta.'
