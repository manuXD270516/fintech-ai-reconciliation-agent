# fintech-ai-reconciliation-agent

Diseño de una plataforma de conciliación de pagos: reglas determinísticas primero, investigación con IA sólo cuando aporta contexto y aprobación humana para decisiones operativas.

**Estado: diseño y especificaciones; aplicación no implementada.** Este directorio es la preparación local de un futuro repositorio público; todavía no se ha publicado en GitHub. Ninguna cifra de desempeño representa un benchmark ejecutado.

## Documentación

| Entregable | Documento |
|---|---|
| 1. Domain analysis | [Dominio e invariantes](docs/01-domain.md#dominio) |
| 2. Bounded contexts | [Límites y propiedad de datos](docs/01-domain.md#bounded-contexts) |
| 3. Actors | [Actores y permisos](docs/01-domain.md#actores) |
| 4. Principal use cases | [Casos de uso](docs/01-domain.md#casos-de-uso) |
| 5. Architecture proposal; NestJS vs FastAPI | [Arquitectura y decisiones](docs/02-architecture.md) |
| 6. C4 context | [Contexto C4](docs/03-c4.md#c4-context) |
| 7. C4 container model | [Contenedores C4](docs/03-c4.md#c4-container-model) |
| 8. Agent responsibilities | [Investigación y revisión humana](docs/04-agents.md) |
| 9. MCP design | [fintech-mcp-server](docs/05-mcp.md) |
| 10. RAG design | [Knowledge base híbrida](docs/06-rag.md) |
| 11. Eval strategy | [Datasets, métricas y gates](docs/07-evals.md) |
| 12. Risk analysis | [Riesgos, seguridad y observabilidad](docs/08-risks.md) |
| 13. Milestone roadmap | [M0–M10](docs/09-roadmap.md) |

## Primer change OpenSpec

[bootstrap-mvp-foundation](openspec/changes/bootstrap-mvp-foundation/proposal.md) especifica **M0**, la base técnica para el MVP. El MVP funcional abarca M1–M6, con un change independiente por capacidad y evals incrementales desde M1. M7 consolida el framework; M8–M10 completan la experiencia pública.

Artefactos: [proposal](openspec/changes/bootstrap-mvp-foundation/proposal.md), [requirements](openspec/changes/bootstrap-mvp-foundation/specs/repository-foundation/spec.md), [acceptance criteria](openspec/changes/bootstrap-mvp-foundation/acceptance-criteria.md), [design](openspec/changes/bootstrap-mvp-foundation/design.md), [tasks](openspec/changes/bootstrap-mvp-foundation/tasks.md), [test strategy](openspec/changes/bootstrap-mvp-foundation/test-strategy.md).

Validación documental desde este directorio, usando OpenSpec 1.11.0:

```text
openspec validate bootstrap-mvp-foundation --strict --no-interactive
openspec status --change bootstrap-mvp-foundation
```

No ejecutar `apply` ni archivar este change mientras siga pendiente su implementación. `openspec/specs/` permanecerá vacío hasta integrar un change implementado y verificado. La presencia de artefactos completos no significa que el software esté construido.

## Límites de la demostración

Datos y proveedores sintéticos. Sin PAN, CVV, credenciales reales, dinero real ni ejecución de reembolsos o ajustes contables. El sistema conserva observaciones y evidencia; no sustituye al ledger ni al procesador de pagos. Toda decisión operativa exige una identidad humana autorizada, incluso si la IA expresa alta confianza.

Las decisiones técnicas son propuestas para este proyecto. Las capacidades externas consultadas se enlazan en [fuentes](docs/10-sources.md); las versiones de dependencias se fijarán y verificarán al implementar M0.
