# ADR-0002: PWA primero, TWA (Google Play) cuando haya demanda

- **Estado**: aceptado
- **Fecha**: 2026-06-14
- **Decisores**: Julio (+ Claude Code)
- **Relacionado**: PLAN MAESTRO §3.1, §4 (Capa 1), §S4.3, §P.4

## Contexto
Los usuarios de Setex capturan facturas desde el móvil. La v1 ya se usa como app instalable. Se necesita
experiencia tipo app (instalable, cámara, offline básico) sin el coste de mantener apps nativas iOS/Android
y sus procesos de publicación, especialmente en fase MVP.

## Decisión
Construir el frontend como **PWA** (React + Vite + `vite-plugin-pwa`): instalable, con service worker,
manifest por tenant (S4.3) y captura con `getUserMedia`. Cuando exista demanda comercial, **envolver la PWA
en una TWA** (Trusted Web Activity) para publicarla en Google Play (tarea P.4, ~1 día), reutilizando la
misma base de código (HTTPS + service worker + `assetlinks.json` ya preparados).

## Alternativas consideradas
- **App nativa (Swift/Kotlin) o React Native/Flutter**: mejor acceso a APIs nativas, pero duplica el
  desarrollo y añade ciclos de revisión de tiendas. Innecesario para el MVP.
- **Solo web responsive (sin PWA)**: pierde instalación, offline y sensación de app que los usuarios ya
  tienen en la v1.

## Consecuencias
- (+) Una sola base de código web; despliegue inmediato sin tiendas.
- (+) Camino a Google Play barato (TWA) cuando se quiera.
- (−) iOS limita algunas capacidades PWA (notificaciones, instalación); aceptable para el caso de uso.
- (−) El acceso a cámara/calidad depende del navegador; se mitiga con los checks de captura (plan §4).
