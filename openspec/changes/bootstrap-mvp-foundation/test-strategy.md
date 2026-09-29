# Estrategia de pruebas — M0

Plan, no suite implementada. Probar contratos y fallas reales, sin tests de “clase existe” ni reglas financieras no especificadas. No requiere modelos.

| ID | Nivel / caso | Método y oráculo |
|---|---|---|
| T01 | Entorno limpio | Guía locked en Linux soportado y smoke Compose desde Windows/WSL2; reportar versiones y plataforma, sin tooling global no declarado |
| T02 | Prerrequisito faltante | Omitir requisito en entorno aislado; verificar corrección en diagnóstico o guía |
| T03 | Infraestructura real | DB confirma extensión/operación vectorial; publicar mensaje y consumir con ack durable en JetStream real |
| T04 | Persistencia | Marcador DB y mensaje pendiente sobreviven stop/start; limpiar sólo recursos propios de test |
| T05 | HTTP sano | Live/ready, schema/status y ausencia de detalles sensibles con dependencias reales |
| T06 | HTTP degradado | DB caída, JetStream no disponible, vector ausente y dependencia colgada, por separado; ready 503 <= 3 s, live 200, recuperación al restablecer |
| T07 | Config inválida | Campo ausente/valor inválido; salida no cero y error sin valor secreto |
| T08 | Defaults/aislamiento | Compose efectivo y puertos: API loopback, DB/bus privados; ignore de secretos y secret scan |
| T09 | Correlación/redacción | IDs válidos/ausentes/malformados; header/log JSON y secreto canario ausente; sin log injection |
| T10 | Gate reproducible | Mismos checks local/CI sin claves de modelos; comparar checks y códigos de salida |
| T11 | Gate negativo | En copia temporal romper spec/contrato y quitar test strategy; cada defecto bloquea gate sin mutar árbol real |
| T12 | Alcance | Rutas sólo health/docs; README sin afirmaciones de implementación o mediciones no respaldadas |
| T13 | Trazabilidad | Revisar AC→RF/T/task, artefactos y evidencia; no archivar sin implementación verificada |

## Ejecución y evidencias

Tests de contrato permiten inyección controlada de fallas para deadlines determinísticos y se complementan con integración real. No sustituir smoke Docker fallido por simulación. Aislar volúmenes/streams con prefijo único y limpiar sólo recursos de esa ejecución. CI usa datos sintéticos efímeros.

Guardar commit, comandos, versiones, SO/arquitectura, resultado/test, logs sanitizados y duración. Infraestructura real puede reportarse MEASURED con ese alcance; no extrapolar a accuracy ni IA. Check omitido = SKIPPED con razón, no satisface aceptación. Los comandos de lint/type/test/smoke se fijarán junto a versiones al implementar. Comando documental actual: `openspec validate bootstrap-mvp-foundation --strict --no-interactive`.

## Stop condition

En esta entrega sólo validar estructura documental, enlaces y consistencia. No crear tests ejecutables, endpoints, contenedores, modelos ni CI. T01–T13 se ejecutan en la implementación posterior de M0.
