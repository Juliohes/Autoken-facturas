// Términos del servicio (LSSI-CE art. 10 + condiciones de contratación). Contenido redactado a
// partir de los requisitos legales vigentes en España para un SaaS B2B (aviso legal, condiciones de
// acceso, rol de encargado del tratamiento frente a los datos de las facturas). Ver companyInfo.ts
// para los datos identificativos pendientes de rellenar y la advertencia de revisión legal.
import type { AppliedTheme } from '../tenancy/theme'
import { COMPANY_INFO } from './companyInfo'
import { LegalDraftNotice, LegalHeading as H2, LegalLayout } from './LegalLayout'

export function TerminosScreen({ theme }: { theme: AppliedTheme }) {
  return (
    <LegalLayout theme={theme} title="Términos del servicio" lastUpdated="3 de septiembre de 2026">
      <LegalDraftNotice />

      <section className="space-y-2">
        <H2>1. Quién presta el servicio</H2>
        <p>
          Autofactu es un servicio prestado por <strong>{COMPANY_INFO.razonSocial}</strong>, con NIF{' '}
          {COMPANY_INFO.nif}, domicilio en {COMPANY_INFO.domicilio}
          {COMPANY_INFO.registroMercantil !== '[DATOS REGISTRALES PENDIENTES DE COMPLETAR]' && (
            <> e inscrita en {COMPANY_INFO.registroMercantil}</>
          )}
          . Puedes contactar con nosotros en{' '}
          <a className="tn-auth-link" href={`mailto:${COMPANY_INFO.emailContacto}`}>
            {COMPANY_INFO.emailContacto}
          </a>
          .
        </p>
      </section>

      <section className="space-y-2">
        <H2>2. Qué es Autofactu</H2>
        <p>
          Autofactu es una aplicación en la nube (SaaS) dirigida a gestorías y asesorías, que
          permite digitalizar facturas (captura por cámara, subida de archivos, reconocimiento
          automático de datos mediante OCR), organizarlas por empresa cliente, revisarlas y
          confirmarlas, y consultar un historial. Cada gestoría (en adelante, el "cliente" o "la
          gestoría") gestiona sus propios usuarios y las empresas de sus clientes dentro de su
          propio espacio, separado del de cualquier otra gestoría.
        </p>
      </section>

      <section className="space-y-2">
        <H2>3. Alta y acceso</H2>
        <p>
          El alta de una gestoría en Autofactu se realiza a través del formulario de registro y
          queda sujeta a la aprobación de un administrador. Cada usuario adicional dentro de una
          gestoría es dado de alta o aprobado por el administrador de esa gestoría, no por Autoken.
        </p>
        <p>
          Eres responsable de mantener la confidencialidad de tu contraseña y, si la tienes
          activada, de tu segundo factor de verificación (TOTP), así como de toda la actividad que
          ocurra con tu cuenta. Debes avisarnos si sospechas de un acceso no autorizado.
        </p>
        <p>
          Los datos que facilitas al registrarte (email, razón social, CIF) deben ser veraces y
          corresponder a una gestoría o profesional real. Un alta con datos falsos o fraudulentos
          puede ser rechazada o, si ya estaba activa, suspendida.
        </p>
      </section>

      <section className="space-y-2">
        <H2>4. Uso correcto del servicio</H2>
        <p>Al usar Autofactu te comprometes a:</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>Usarlo únicamente para la gestión de facturas propias o de tus clientes, dentro de tu actividad profesional.</li>
          <li>No intentar acceder a datos de otra gestoría, ni a funciones para las que no tengas permiso.</li>
          <li>No usar el servicio para subir documentos que no sean facturas o justificantes legítimos, ni contenido ilícito.</li>
          <li>No interferir con el funcionamiento del servicio (por ejemplo, con ataques automatizados o intentos de sobrecarga).</li>
        </ul>
      </section>

      <section className="space-y-2">
        <H2>5. Los datos de las facturas: quién es responsable de qué</H2>
        <p>
          Es importante distinguir dos tipos de datos:
        </p>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <strong>Datos de tu cuenta</strong> (tu email, tu contraseña cifrada, tu rol): aquí
            Autoken es <strong>responsable del tratamiento</strong>, tal y como se explica en
            nuestra{' '}
            <a className="tn-auth-link" href="/privacidad">
              Política de Privacidad
            </a>
            .
          </li>
          <li>
            <strong>Los datos contenidos en las facturas que subes</strong> (por ejemplo, datos de
            proveedores, clientes o empleados de las empresas que gestionas) son responsabilidad de
            tu gestoría o de la empresa a la que pertenecen esas facturas. Respecto a esos datos,
            Autoken actúa como <strong>encargado del tratamiento</strong> (art. 28 del RGPD): los
            tratamos únicamente para prestar el servicio (almacenarlos, procesarlos con OCR,
            mostrártelos), siguiendo tus instrucciones, y nunca los usamos con fines propios ni los
            cedemos a terceros salvo obligación legal (por ejemplo, verificación fiscal ante la
            Agencia Tributaria cuando la propia función del servicio lo requiere).
          </li>
        </ul>
        <p>
          Si tu gestoría necesita un contrato de encargo del tratamiento formal (documento aparte,
          firmado) para cumplir tus propias obligaciones de RGPD frente a tus clientes, escríbenos a{' '}
          {COMPANY_INFO.emailContacto} y te lo facilitamos.
        </p>
      </section>

      <section className="space-y-2">
        <H2>6. Disponibilidad y soporte</H2>
        <p>
          Trabajamos para que el servicio esté disponible de forma continua, pero al ser un
          servicio en la nube puede haber interrupciones puntuales (mantenimiento, incidencias
          técnicas, causas de fuerza mayor). No garantizamos una disponibilidad del 100% y no
          respondemos de los daños derivados de una interrupción, salvo negligencia grave por
          nuestra parte.
        </p>
      </section>

      <section className="space-y-2">
        <H2>7. Propiedad intelectual</H2>
        <p>
          El software, el diseño y la marca de Autofactu son propiedad de {COMPANY_INFO.razonSocial}
          {' '}o de sus licenciantes. El contenido que subes (tus facturas y los datos que contienen)
          sigue siendo tuyo o de tu gestoría; nosotros solo lo tratamos para prestarte el servicio.
        </p>
      </section>

      <section className="space-y-2">
        <H2>8. Suspensión y baja</H2>
        <p>
          Podemos suspender o cancelar una cuenta que incumpla estos términos, que suponga un riesgo
          de seguridad para el servicio o para otras gestorías, o por impago si el servicio es de
          pago. Puedes solicitar la baja de tu cuenta escribiendo a {COMPANY_INFO.emailContacto};
          conservaremos los datos que estemos legalmente obligados a conservar (ver la sección de
          plazos de conservación de la Política de Privacidad) incluso después de la baja.
        </p>
      </section>

      <section className="space-y-2">
        <H2>9. Cambios en estos términos</H2>
        <p>
          Podemos actualizar estos términos para reflejar cambios en el servicio o en la normativa
          aplicable. Si el cambio es significativo, te avisaremos por email o mediante un aviso en
          la aplicación antes de que entre en vigor.
        </p>
      </section>

      <section className="space-y-2">
        <H2>10. Legislación aplicable</H2>
        <p>
          Estos términos se rigen por la legislación española. Cualquier controversia se someterá a
          los juzgados y tribunales que correspondan según la normativa de protección de
          consumidores y usuarios que resulte aplicable.
        </p>
      </section>
    </LegalLayout>
  )
}
