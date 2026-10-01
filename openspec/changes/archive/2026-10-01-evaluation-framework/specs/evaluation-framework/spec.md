## ADDED Requirements

### Requirement: RF-01 Single runner with versioned manifests

El sistema SHALL ejecutar todas las suites con un único runner y MUST describir cada suite en un manifest versionado con dataset, versión, semilla u origen, política de split, etiquetas, acciones prohibidas cuando aplique y gates con umbral, dirección y criticidad.

#### Scenario: Run selected suites
- **WHEN** se ejecuta el runner con una lista de suites
- **THEN** produce un reporte JSON y Markdown con un resultado por suite y los gates de su manifest

### Requirement: RF-02 Honest labels and denominators

Cada resultado SHALL etiquetarse MEASURED (componente real sobre datos sintéticos), SIMULATED (salida de modelo scripted) o SKIPPED (dependencia ausente); un SKIPPED MUST NOT contener métricas fabricadas. Los umbrales MUST tratarse como EXPECTED. Una tasa con denominador cero MUST reportarse como N/A y las proporciones principales MUST incluir n e intervalo de Wilson del 95 %.

#### Scenario: Missing database
- **WHEN** la suite de retrieval corre sin PostgreSQL
- **THEN** su resultado es SKIPPED, sin métricas, y no bloquea

### Requirement: RF-03 Leakage-free splits

Las suites con splits SHALL asignar filas por familia (no por fila) y MUST verificar que ninguna familia aparezca en dos splits. Las etiquetas gold MUST provenir de una fuente independiente del componente evaluado y no entrar en sus entradas.

#### Scenario: Reconciliation split
- **WHEN** se evalúan 1210 pagos en 121 familias
- **THEN** el reporte muestra cero familias filtradas entre dev, calibration y holdout

### Requirement: RF-04 Module suites

El framework SHALL incluir suites de conciliación (accuracy, precision/recall de EXACT, falsos EXACT, F1 por clase y de discrepancias, matriz de confusión), retrieval (métricas de M3 por modo y split), contratos de tools MCP, investigación (estado esperado, precisión de selección de tools, ejecuciones prohibidas, hechos sin soporte, violaciones de presupuesto, completitud, variabilidad entre repeticiones) y aprobación humana (intentos inválidos bloqueados, válidos permitidos, autoaprobaciones).

#### Scenario: Investigation guards
- **WHEN** se corren los escenarios adversariales de investigación
- **THEN** el reporte muestra cero ejecuciones de tools prohibidas y cero hechos sin soporte en borradores finales

### Requirement: RF-05 Critical gates block release

Un gate crítico fallido SHALL marcar la suite y el reporte como FAIL y MUST hacer fallar el paso `evals` del gate de calidad, que CI ejecuta en el mismo orden. Los gates no críticos MUST reportarse sin bloquear.

#### Scenario: Injected failure
- **WHEN** una suite produce un valor que viola un gate crítico
- **THEN** el comando de gate termina con código distinto de cero

### Requirement: RF-06 Regression detection against a baseline

El gate SHALL comparar las métricas con gate contra un baseline versionado y MUST fallar si una métrica empeora en la dirección de su gate más allá de la tolerancia (o cambia en métricas de igualdad).

#### Scenario: Recall drops
- **WHEN** una métrica `>=` baja más de 0.02 respecto del baseline
- **THEN** se informa como regresión y el gate falla

### Requirement: RF-07 Reproducible reports

Cada reporte SHALL incluir commit, si el árbol tenía cambios, host, versión de Python, momento, duración, suites pedidas, manifests (con hash de contenido de los datasets generados), métricas, gates, notas y una muestra de fallos.

#### Scenario: Report metadata
- **WHEN** se genera un reporte
- **THEN** contiene commit, `dirty`, host y el hash de contenido del dataset de conciliación
