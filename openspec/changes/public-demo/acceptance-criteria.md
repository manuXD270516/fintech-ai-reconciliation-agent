# Criterios de aceptación — public-demo

Un criterio sólo pasa a **PASS** con evidencia enlazada. IDs RF: [requirements](specs/public-demo/spec.md); IDs T: [test strategy](test-strategy.md); IDs numéricos: [tasks](tasks.md). Detalle: [evidencia](evidence/README.md).

| ID | Criterio observable | Requirements | Tests | Tasks | Estado | Evidencia |
|---|---|---|---|---|---|---|
| AC01 | Sesiones de demo reproducibles con resultados iguales a las etiquetas y aisladas entre sí | RF-01 | T01, T02 | 1.1 | PASS | [evidencia](evidence/README.md#por-criterio) |
| AC02 | Con la IA apagada, el flujo humano y la conciliación siguen funcionando; las investigaciones se rechazan con un código claro | RF-02 | T03 | 1.2 | PASS | [evidencia](evidence/README.md#por-criterio) |
| AC03 | Walkthrough y ficha de datasets con límites visibles | RF-03 | T05 | 2.1 | PASS | [evidencia](evidence/README.md#por-criterio) |
| AC04 | Resultados sanitizados con etiquetas y evidencia; sin rutas personales ni secretos; licencias inventariadas; recursos medidos | RF-04 | T04, T05 | 2.2 | PASS | [evidencia](evidence/README.md#por-criterio) |
| AC05 | Nada publicado ni desplegado; decisiones del propietario documentadas; gate completo verde | RF-05 | T05 | 2.3 | PASS | [evidencia](evidence/README.md#por-criterio) |

Definition of Done de M10: AC01–AC05 en PASS con evidencia. El CI remoto sigue cubierto por AC06 de M0 (PENDING por facturación de GitHub).
