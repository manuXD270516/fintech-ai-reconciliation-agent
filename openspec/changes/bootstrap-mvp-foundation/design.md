## Context

Ver [proposal](proposal.md) para motivación. Directorio nuevo, sin software ni infraestructura existente. OpenSpec 1.11.0 con schema `spec-driven`. La [arquitectura objetivo](../../../docs/02-architecture.md) cubre M0–M10; este change sólo prepara M0 cuando se implemente.

## Goals / Non-Goals

**Goals:** entorno reproducible, diagnóstico fiable y calidad antes de recibir pagos; dominio desacoplado y procesos futuros sin servicios vacíos innecesarios.

**Non-Goals:** modelos, agentes, MCP, RAG, frontend, benchmark de accuracy, integraciones reales o publicación remota.

## Decisions

### D1 — Base Python y API mínima

FastAPI por continuidad con investigación/evals en Python, según ADR-001. Sólo health endpoints y documentación técnica. `apps/api` contiene adaptador HTTP; futuras reglas vivirán fuera. Describir límites de `packages/domain` sin crear clases vacías. React no se incorpora hasta M8; OpenSpec es herramienta de desarrollo independiente.

Versiones soportadas iniciales propuestas: Python 3.12, PostgreSQL 17, NATS 2.x con JetStream y pgvector compatible. Tareas 1.2/2.1 fijarán versiones exactas, hashes/digests tras verificar compatibilidad y seguridad; no usar `latest`. uv con lockfile para Python y OpenSpec 1.11.0 fijado como herramienta de desarrollo. No son afirmaciones sobre últimas versiones.

### D2 — Docker Compose y ciclo local

Ruta soportada: API, PostgreSQL/pgvector y NATS en Compose sobre Linux o Windows con Docker Desktop/WSL2. Contributor requiere Docker/Compose, uv (gestiona Python 3.12 y el gate local: lint, tipos, tests, orquestación del smoke) y Node para OpenSpec fijado; ejecutar la API fuera de Compose es opcional y no es ruta soportada. Readiness maneja dependencias arrancando: `depends_on` no sustituye verificación de capacidades.

DB y NATS sólo en red interna; API publicada en `127.0.0.1`. Volúmenes nombrados. Stop conserva datos; reset separado advierte eliminación. Inicialización/migración idempotente de extensión con rol distinto del runtime. Instalaciones manuales descartadas como ruta principal por divergencia de entornos. Locks y contenedores no garantizan reproducibilidad bit a bit entre arquitecturas: reportar plataforma.

### D3 — Health sin efectos de negocio

Live responde proceso. Ready verifica query liviana DB, extensión y consulta de información JetStream. Deadline total 3 s con timeouts por probe y concurrencia cuando haga falta. No escribir filas ni publicar mensajes en cada health request: el smoke separado comprueba roundtrip durable y persistencia con datos sintéticos aislados.

Respuesta mínima: estado general, request ID y estados `database`, `vector`, `messaging`; sin hosts, SQL, URLs o secretos. Config inválida falla temprano. LLM/MCP no son dependencias de M0.

### D4 — Seguridad y telemetry mínimas

Ejemplo local/sintético con credenciales de desarrollo identificadas, red privada y archivos secretos ignorados. Logs JSON con request ID generado/validado, ruta, status y duración. Rechazar o reemplazar IDs malformados para evitar log injection. Sin auth de usuarios en health local M0; esto no autoriza endpoints operativos anónimos ni despliegue público, que exigirán otro change y controles.

### D5 — CI y contratos

Instalación locked → Ruff → mypy → pytest → Compose smoke → validación OpenSpec/artefactos. Fijar versiones al implementar. CI y guía local ejecutan iguales checks. Health tests cubren fallas y timeout; integración comprueba extensión y JetStream reales. No agregar dependencias LLM/embeddings/frontend.

### D6 — Workflow OpenSpec

Schema estándar: proposal, design, specs y tasks; complementos explícitos `acceptance-criteria.md` y `test-strategy.md`. `config.yaml` guía el proyecto, pero CLI estándar no impone todos los seis artefactos ni prueba implementación. Gate adicional verificará presencia y trazabilidad; revisión humana confirma contenido. No se necesita schema personalizado ni agentes editores para bootstrap. En esta fase tasks sin marcar y change sin archivar.

## Risks / Trade-offs

- Docker ausente → diagnóstico, nunca declarar smoke exitoso con mocks.
- Broker sin JetStream → probe de capacidad y test negativo.
- Readiness lento → deadlines por dependencia/global y test con dependencia colgada.
- Defaults locales usados públicamente → loopback y dependencias privadas; alcance explícito.
- Versiones flotantes → locks/digests y revisión de cambios.
- Validación formal sin semántica → matriz requisito/criterio/test/task y evidencia revisada.

## Migration Plan

Sin datos existentes. Implementación futura: archivos bootstrap → entorno aislado → gates → evidencia → integración. Rollback revierte código/config y detiene servicios preservando volúmenes; reset destructivo no es rollback por defecto. Archivar sólo después de implementación y pruebas, integrando entonces specs vigentes.

## Acceptance and Test Strategy

Ver [acceptance criteria](acceptance-criteria.md) y [test strategy](test-strategy.md). No se han ejecutado tests de runtime en esta fase documental.
