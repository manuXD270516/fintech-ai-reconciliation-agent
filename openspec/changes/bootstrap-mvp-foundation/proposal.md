## Why

El proyecto necesita una base reproducible y verificable antes de modelar pagos, procesar eventos o investigar discrepancias con IA. Definir el bootstrap evita confundir infraestructura disponible con un MVP financiero implementado.

## What Changes

- Especificar **M0 — Repository bootstrap**, primera base del MVP M0–M6.
- Preparar, cuando se implemente, estructura modular, dependencias fijadas, API mínima de salud, PostgreSQL con pgvector y NATS JetStream locales.
- Proveer diagnóstico diferenciado de proceso/dependencias, configuración de desarrollo segura y CI sin claves de proveedores IA.
- Hacer reproducibles instalación, arranque, verificación y apagado conservando los datos locales por defecto.
- Exigir trazabilidad entre specs, aceptación, tareas y pruebas; estado público honesto y datos sintéticos.

## Capabilities

### New Capabilities

- `repository-foundation`: un contributor puede preparar el entorno local, levantar servicios base, verificar su salud y ejecutar controles de calidad reproducibles sin credenciales financieras o de IA.

### Modified Capabilities

Ninguna. No existen capacidades implementadas ni specs vigentes previas.

## Impact

En la futura implementación: raíz del repositorio, configuración de desarrollo, API de salud, dependencias/migraciones de infraestructura, CI, tests smoke y documentación de uso. No hay usuarios ni datos existentes que migrar. No cambia contratos de pagos porque todavía no existen.

El estado de implementación y su evidencia están en [tasks](tasks.md), [acceptance criteria](acceptance-criteria.md) y [evidence](evidence/README.md). El check de estructura OpenSpec, por sí solo, no demuestra un servicio funcionando.

## Non-goals

Modelos de transacción, ingestion de pagos, motor de conciliación, RAG, MCP ejecutable, agentes, aprobación operativa, dashboard, datasets ejecutables, benchmark de producto, publicación remota y despliegue público pertenecen a changes posteriores. M0 no instala integraciones con proveedores reales ni ejecuta pagos. El límite READ-only de MCP y la aprobación humana son decisiones para el MVP y permanecen vigentes.
