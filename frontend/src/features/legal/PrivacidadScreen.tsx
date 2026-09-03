// Política de privacidad (RGPD art. 13/14 + LOPDGDD). Contenido mínimo obligatorio: identidad del
// responsable, finalidades, base jurídica, destinatarios, plazos de conservación y derechos de la
// persona interesada. Ver companyInfo.ts para los datos identificativos pendientes de rellenar y la
// advertencia de revisión legal (repetida aquí con LegalDraftNotice, mismo componente que /terminos).
//
// Los "destinatarios" y finalidades reflejan lo que la aplicación hace de verdad (no una plantilla
// genérica): envío de email transaccional por SMTP (notifications/smtp_notifier.py), verificación
// fiscal del CIF/NIF de la contraparte de una factura contra los servicios públicos de la AEAT y
// VIES (counterparty/resolvers/), y ningún analytics ni cookie de terceros (no hay ninguno en el
// frontend, comprobado en el propio código).
import type { AppliedTheme } from '../tenancy/theme'
import { COMPANY_INFO } from './companyInfo'
import { LegalDraftNotice, LegalHeading as H2, LegalLayout } from './LegalLayout'

export function PrivacidadScreen({ theme }: { theme: AppliedTheme }) {
  return (
    <LegalLayout theme={theme} title="Política de privacidad" lastUpdated="3 de septiembre de 2026">
      <LegalDraftNotice />

      <section className="space-y-2">
        <H2>1. Responsable del tratamiento</H2>
        <p>
          <strong>{COMPANY_INFO.razonSocial}</strong>, NIF {COMPANY_INFO.nif}, domicilio en{' '}
          {COMPANY_INFO.domicilio}, es responsable del tratamiento de los datos de cuenta de las
          personas usuarias de Autofactu. Puedes contactar con nosotros para cualquier cuestión
          relacionada con tus datos en{' '}
          <a className="tn-auth-link" href={`mailto:${COMPANY_INFO.emailContacto}`}>
            {COMPANY_INFO.emailContacto}
          </a>
          . No tenemos designado un Delegado de Protección de Datos por no ser obligatorio para
          nuestra actividad, pero cualquier solicitud sobre tus datos se atiende en esa misma
          dirección.
        </p>
      </section>

      <section className="space-y-2">
        <H2>2. Qué datos tratamos</H2>
        <ul className="list-disc space-y-1 pl-5">
          <li><strong>Datos de cuenta:</strong> nombre, email, contraseña (nunca almacenada en claro, solo su hash con Argon2id), rol dentro de tu gestoría.</li>
          <li><strong>Datos de la gestoría/empresa:</strong> razón social, CIF, y las empresas cliente que gestionas dentro de Autofactu.</li>
          <li><strong>Datos técnicos de acceso:</strong> dirección IP y marca de tiempo de inicios de sesión y acciones relevantes (registro de auditoría), para seguridad.</li>
          <li>
            <strong>Contenido de las facturas que subes:</strong> los datos que aparecen en esos
            documentos (que pueden incluir datos de proveedores, clientes o personas físicas,
            como autónomos). Sobre estos datos actuamos como encargados del tratamiento por
            cuenta de tu gestoría, tal y como se explica en los{' '}
            <a className="tn-auth-link" href="/terminos">
              Términos del servicio
            </a>
            , no como responsables.
          </li>
        </ul>
      </section>

      <section className="space-y-2">
        <H2>3. Para qué usamos tus datos y con qué base legal</H2>
        <ul className="list-disc space-y-1 pl-5">
          <li><strong>Prestar el servicio</strong> (gestionar tu cuenta, procesar y mostrar tus facturas): ejecución del contrato de uso del servicio (art. 6.1.b RGPD).</li>
          <li><strong>Verificar tu email y darte de alta</strong>: consentimiento que prestas al registrarte (art. 6.1.a RGPD), revocable en cualquier momento dándote de baja.</li>
          <li><strong>Comunicaciones de servicio</strong> (verificación de email, recuperación de contraseña, avisos de seguridad): ejecución del contrato y nuestro interés legítimo en mantener tu cuenta segura (art. 6.1.b y 6.1.f RGPD).</li>
          <li><strong>Verificación fiscal del CIF/NIF de la contraparte de una factura</strong> ante los servicios públicos de la Agencia Tributaria (AEAT) y el sistema VIES de la Comisión Europea, cuando la propia factura lo requiere: interés legítimo en la exactitud de los datos fiscales que gestionas (art. 6.1.f RGPD).</li>
          <li><strong>Conservar el registro de auditoría y el contenido contable/fiscal</strong> el tiempo legalmente exigido: obligación legal (art. 6.1.c RGPD, ver sección 5).</li>
        </ul>
      </section>

      <section className="space-y-2">
        <H2>4. A quién comunicamos tus datos</H2>
        <p>No vendemos ni cedemos tus datos con fines comerciales o publicitarios. Sí los compartimos, en la medida estrictamente necesaria, con:</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            Nuestro proveedor de correo (Hostinger), únicamente para enviarte los emails de
            verificación, activación, recuperación de contraseña y avisos de registro que tú mismo
            solicitas o que forman parte del servicio.
          </li>
          <li>
            La Agencia Tributaria (AEAT) y el sistema VIES de la Comisión Europea, únicamente el
            CIF/NIF de la contraparte de una factura, para comprobar su validez fiscal.
          </li>
          <li>
            Nuestro proveedor de alojamiento (hosting/VPS), que almacena la infraestructura donde
            corre Autofactu, bajo las garantías de confidencialidad correspondientes.
          </li>
        </ul>
        <p>
          No realizamos transferencias de datos fuera del Espacio Económico Europeo salvo que un
          proveedor de los anteriores lo requiera para prestar su servicio, en cuyo caso se hace
          con las garantías que exige el RGPD (por ejemplo, cláusulas contractuales tipo).
        </p>
      </section>

      <section className="space-y-2">
        <H2>5. Cuánto tiempo conservamos tus datos</H2>
        <ul className="list-disc space-y-1 pl-5">
          <li><strong>Datos de cuenta:</strong> mientras tu cuenta esté activa, y hasta que solicites la baja.</li>
          <li>
            <strong>Contenido contable/fiscal (facturas y sus datos):</strong> el plazo que exige
            la normativa mercantil española, hasta 6 años desde el último asiento realizado en los
            libros a los que se refieren (art. 30 del Código de Comercio), aunque hayas dejado de
            usar el servicio.
          </li>
          <li><strong>Registro de auditoría:</strong> el mismo plazo, como respaldo de la integridad de la información anterior.</li>
        </ul>
      </section>

      <section className="space-y-2">
        <H2>6. Tus derechos</H2>
        <p>Puedes ejercer en cualquier momento, escribiendo a {COMPANY_INFO.emailContacto}:</p>
        <ul className="list-disc space-y-1 pl-5">
          <li><strong>Acceso:</strong> saber qué datos tuyos tratamos.</li>
          <li><strong>Rectificación:</strong> corregir datos inexactos.</li>
          <li><strong>Supresión:</strong> pedir que borremos tus datos (salvo los que debamos conservar por obligación legal, ver sección 5).</li>
          <li><strong>Oposición y limitación:</strong> oponerte a un tratamiento concreto o pedir que se limite mientras se resuelve una solicitud.</li>
          <li><strong>Portabilidad:</strong> recibir tus datos en un formato estructurado para llevarlos a otro proveedor.</li>
        </ul>
        <p>
          Si consideras que no hemos atendido bien tu solicitud, puedes reclamar ante la Agencia
          Española de Protección de Datos (
          <a className="tn-auth-link" href="https://www.aepd.es" target="_blank" rel="noreferrer">
            www.aepd.es
          </a>
          ).
        </p>
      </section>

      <section className="space-y-2">
        <H2>7. Seguridad</H2>
        <p>
          Tus contraseñas se guardan cifradas con Argon2id (nunca en texto plano), ofrecemos
          verificación en dos pasos (TOTP) para las cuentas de administración, y los datos de cada
          gestoría están aislados de los de las demás a nivel de base de datos, no solo de
          pantalla.
        </p>
      </section>

      <section className="space-y-2">
        <H2>8. Cookies y almacenamiento local</H2>
        <p>
          Autofactu usa una cookie técnica, estrictamente necesaria para mantener tu sesión iniciada
          de forma segura, y el almacenamiento local de tu navegador para recordar tus preferencias
          de interfaz (por ejemplo, el tema claro u oscuro). Ninguna de las dos requiere tu
          consentimiento por ser estrictamente técnicas (art. 22.2 LSSI-CE). No usamos cookies ni
          herramientas de terceros con fines de analítica o publicidad.
        </p>
      </section>

      <section className="space-y-2">
        <H2>9. Menores de edad</H2>
        <p>
          Autofactu es una herramienta profesional dirigida a gestorías y asesorías. No está
          dirigida a menores de edad y no recogemos deliberadamente datos de menores.
        </p>
      </section>

      <section className="space-y-2">
        <H2>10. Cambios en esta política</H2>
        <p>
          Si cambiamos esta política de forma significativa, te avisaremos por email o mediante un
          aviso en la aplicación antes de que entre en vigor.
        </p>
      </section>
    </LegalLayout>
  )
}
