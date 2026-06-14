# ADR-0005: Hostinger + Docker Compose ahora; portable a AWS sin reescritura

- **Estado**: aceptado (asignación de VPS matizada por ADR-0009)
- **Fecha**: 2026-06-14
- **Decisores**: Julio (+ Claude Code)
- **Relacionado**: PLAN MAESTRO §5

## Contexto
Hay que elegir dónde y cómo desplegar el MVP. Existen dos VPS Hostinger (KVM 2). Se busca arrancar rápido y
barato sin quedar atrapados en un proveedor, manteniendo la opción de migrar a un cloud mayor (AWS) si el
crecimiento lo exige.

## Decisión
Desplegar todo con **Docker Compose** (servicios: `caddy`, `api`, `worker`, `postgres`, `redis`, `minio`,
`clamav`) sobre **VPS de Hostinger**:
- **VPS B `2.24.8.109`**: se construye la v2 (staging en desarrollo) y nace **producción** en el go-live.
- **VPS A `72.60.186.89`**: ejecuta la v1 en producción; **no se toca** salvo hardening de acceso; tras la
  retirada de la v1 se limpia y pasa a staging definitivo.
- Al ser 100% contenedores, la pila es **portable a cualquier proveedor (incluido AWS)** sin reescritura.
- Señal de upgrade (KVM 2 → 4): RAM sostenida > 75% o cola OCR con esperas > 2 min (monitorizado en Grafana).

## Alternativas consideradas
- **AWS/GCP gestionado desde el inicio (ECS/RDS/S3...)**: más escalable y con más piezas gestionadas, pero
  mayor coste y complejidad operativa para un MVP; riesgo de acoplamiento a servicios propietarios.
- **PaaS (Render/Fly/Railway)**: cómodo pero menos control y peor encaje con los dos VPS ya disponibles.

## Consecuencias
- (+) Arranque barato y rápido con infra ya disponible; misma pila en local, staging y producción.
- (+) Migración futura a AWS factible (mismas imágenes Docker) sin reescritura.
- (−) Más responsabilidad operativa propia (backups, parches, monitorización) — cubierta por runbooks y
  Sprint 5.
- **Nota**: el alcance del hardening del VPS A se redujo por ser producción activa (ver **ADR-0009**).
