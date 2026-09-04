// Copia de la política de contraseñas para mostrarla en la UI. Fuente real:
// backend/src/identity/passwords.py::validate_password_policy + shared/config.py
// (password_min_length=12, password_max_length=128) -- solo longitud, sin exigir mayúsculas,
// dígitos ni símbolos (ADR-0012). El backend no expone este número por ninguna API pública, así que
// aquí se copia a mano: si algún día se cambia `PASSWORD_MIN_LENGTH` en el `.env`, hay que
// actualizar también este texto para que no diverja.
//
// Hallazgo real (Julio, 2026-09-03): al registrarse en setex.autoken.es le salió "password does not
// meet policy" sin que la pantalla dijera en ningún sitio cuál era esa política.
export const PASSWORD_POLICY_HINT = 'Mínimo 12 caracteres. No hace falta mayúsculas, números ni símbolos.'
export const PASSWORD_POLICY_ERROR =
  'La contraseña no cumple los requisitos: debe tener al menos 12 caracteres.'

// Texto EXACTO que responde el backend (identity/registration_router.py, identity/router.py,
// identity/password_reset_router.py) cuando `validate_password_policy` rechaza la contraseña.
// Mismo patrón que PENDING_OCR_DETAIL/CAPTURE_UNREADABLE_DETAIL en confirmation/useReview.ts:
// comparar contra el `detail` crudo del backend para traducirlo, no adivinarlo por el código HTTP
// (que también es 422 para un CIF inválido, cuyo mensaje SÍ ya viene en español y hay que dejarlo
// pasar tal cual).
export const WEAK_PASSWORD_DETAIL = 'password does not meet policy'
