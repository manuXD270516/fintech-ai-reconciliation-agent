# Fuentes técnicas y alcance de las decisiones

Consultadas el 23 de septiembre de 2026. Las fuentes respaldan capacidades de herramientas; la elección, la arquitectura, los contratos y los targets de este repositorio son propuestas propias, no garantías de proveedores.

| Fuente primaria | Uso en la propuesta |
|---|---|
| [FastAPI: concurrency and async/await](https://fastapi.tiangolo.com/async/) | Separación entre concurrencia de I/O y trabajo intensivo; no inferir throughput sin benchmark |
| [NestJS: microservices](https://docs.nestjs.com/microservices/basics) | Alternativa con abstracciones de transporte; comparación de integración, no superioridad absoluta |
| [pgvector](https://github.com/pgvector/pgvector) | Vector search exacto/aproximado, filtros, combinación con PostgreSQL full-text y RRF |
| [NATS JetStream](https://docs.nats.io/concepts/jetstream) | Persistencia/consumidores; diseño con at-least-once y deduplicación propia |
| [MCP tools, revisión 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) | Contratos de tools, structured outputs y anotaciones; protocolo a fijar/verificar en M4 |
| [OpenSpec: spec-driven schema](https://openspec.dev/docs/schemas/spec-driven) | Relación proposal/specs/design/tasks y separación apply |
| [Repositorio oficial OpenSpec](https://github.com/Fission-AI/OpenSpec) | Workflow de changes y especificaciones delta |

Para el change actual se consultaron también las instrucciones del CLI **OpenSpec 1.11.0 instalado localmente** mediante `openspec instructions` y `openspec templates`. Éstas determinan el formato validado, incluyendo `## Purpose`, `## ADDED Requirements`, `### Requirement` y `#### Scenario`.
