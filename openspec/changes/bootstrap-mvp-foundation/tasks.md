## 1. Preparación reproducible

- [ ] 1.1 Crear estructura mínima de API y guía sin lógica de pagos; verificar T01/T02 y AC01 en checkout limpio.
- [ ] 1.2 Fijar Python/dependencias, uv lock y OpenSpec; verificar instalación locked mediante T01 (AC01).
- [ ] 1.3 Documentar configuración sintética y archivos ignorados; verificar T02/T07/T08 (AC01/AC04).

## 2. Infraestructura local

- [ ] 2.1 Preparar Compose DB/vector, JetStream, API loopback y volúmenes con versiones/digests fijados; comprobar T03/T08 (AC02/AC04).
- [ ] 2.2 Agregar inicialización idempotente de extensión y roles restringidos; verificar vector y roundtrip durable con T03 sin permisos de inicialización en runtime (AC02).
- [ ] 2.3 Documentar start/stop y reset separado; comprobar persistencia DB/mensajería con T04 (AC02).

## 3. API de salud y diagnóstico

- [ ] 3.1 Implementar live/ready con contrato mínimo y probes acotados; verificar T05 (AC03).
- [ ] 3.2 Cubrir DB caída, vector ausente, JetStream indisponible y timeout; verificar deadline/recuperación con T06 (AC03).
- [ ] 3.3 Implementar validación de configuración y logs/request IDs sanitizados; verificar T07/T09 (AC04/AC05).

## 4. Gates de desarrollo

- [ ] 4.1 Configurar lint, tipos, tests y smoke real documentados; verificar ejecución sin claves IA con T10 (AC06).
- [ ] 4.2 Agregar gate OpenSpec y presencia/trazabilidad de seis artefactos; comprobar fallos aislados con T11/T13 (AC06/AC08).
- [ ] 4.3 Configurar CI con iguales checks; verificar éxito y fallo intencional de contrato con T10/T11 (AC06).

## 5. Evidencia y cierre

- [ ] 5.1 Actualizar README al alcance M0 implementado; verificar rutas/etiquetas mediante T12 (AC07).
- [ ] 5.2 Ejecutar y enlazar T01–T13 contra [aceptación](acceptance-criteria.md) siguiendo [test strategy](test-strategy.md); mantener omitidos pendientes (AC01–AC08).
- [ ] 5.3 Revisar resultados, completar tasks sólo con evidencia y archivar/integrar specs únicamente después de implementar y verificar; comprobar T13 (AC08).
