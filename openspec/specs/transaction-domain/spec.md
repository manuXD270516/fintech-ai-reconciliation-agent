# transaction-domain Specification

## Purpose
Representar y persistir observaciones sintéticas de transacciones con dinero exacto, identidad acotada, revisiones idempotentes y lotes explícitos, como base verificable para la conciliación determinística.

## Requirements

### Requirement: RF-01 Exact money

El dominio SHALL representar importes como enteros en unidad menor con una moneda cuyo exponente está definido en una política versionada. La conversión desde decimal MUST ser exacta y MUST rechazar floats, valores no finitos, precisión mayor al exponente, monedas no soportadas y valores fuera del rango de 64 bits con signo.

#### Scenario: Exact decimal roundtrip
- **WHEN** un importe válido se convierte a decimal y de vuelta en la misma moneda
- **THEN** se obtiene exactamente el mismo valor en unidades menores

#### Scenario: Excess precision
- **WHEN** se recibe `10.005` para USD (exponente 2)
- **THEN** la conversión se rechaza sin redondear

#### Scenario: Cross-currency arithmetic
- **WHEN** se intenta sumar o restar importes de monedas distintas
- **THEN** la operación se rechaza porque FX está fuera de alcance

### Requirement: RF-02 Immutable scoped observations

Una observación SHALL ser inmutable y contener tenant, fuente, ID de registro, revisión, proveedor, cuenta, operación, referencias, dinero, estado, timestamps de ocurrencia y recepción con offset original y UTC, hash del registro original y versión de normalización. Las referencias externas MUST estar acotadas por proveedor y cuenta, y dos observaciones MUST NOT considerarse comparables si difieren en tenant, proveedor, cuenta, moneda u operación, o si provienen de la misma fuente.

#### Scenario: Naive timestamp
- **WHEN** una fuente entrega un timestamp sin offset
- **THEN** la observación se rechaza en lugar de asumir una zona horaria

#### Scenario: Scope isolation
- **WHEN** dos observaciones comparten referencia pero pertenecen a cuentas o monedas distintas
- **THEN** no son comparables

### Requirement: RF-03 Idempotent revisions

La ingesta SHALL clasificar cada observación respecto a la historia de su clave (tenant, fuente, ID de registro). Un replay con la misma revisión y hash MUST NOT crear filas, auditoría ni eventos; misma revisión con otro hash MUST registrarse como conflicto sin sobrescribir; una revisión mayor se convierte en vigente y una revisión menor no vista se conserva como historia.

#### Scenario: Transport replay
- **WHEN** llega dos veces la misma revisión con el mismo contenido
- **THEN** la segunda entrega devuelve el ID existente sin nuevos efectos

#### Scenario: Conflicting content
- **WHEN** llega la misma revisión con distinto hash
- **THEN** se audita un conflicto y la fila original permanece intacta

#### Scenario: Out-of-order revision
- **WHEN** la revisión 2 llega después de la revisión 3
- **THEN** se conserva como historia y la revisión vigente sigue siendo 3

### Requirement: RF-04 Reconciliation batches

Un lote SHALL definir tenant, proveedor, cuenta, moneda, ventana semiabierta `[inicio, fin)` en UTC, zona horaria de negocio IANA válida, un par de fuentes distintas y un cutoff no anterior al fin de la ventana. Un lote MUST admitir sólo observaciones de su alcance y ventana y MUST NOT considerarse cerrado antes del cutoff.

#### Scenario: Window boundary
- **WHEN** una observación ocurre exactamente en el fin de la ventana
- **THEN** no pertenece al lote

#### Scenario: Invalid batch
- **WHEN** la ventana está vacía, el cutoff es anterior al fin o las fuentes coinciden
- **THEN** el lote se rechaza

### Requirement: RF-05 Versioned source mappings

El sistema SHALL traducir estados y operaciones específicos de cada fuente y proveedor mediante vocabularios versionados. Un valor sin mapping MUST rechazarse con un error identificable para cuarentena y MUST NOT adivinarse.

#### Scenario: Unknown provider status
- **WHEN** un proveedor reporta un estado no mapeado
- **THEN** la traducción falla con un error de mapping que indica fuente, proveedor y versión

### Requirement: RF-06 Versioned synthetic fixtures

El repositorio SHALL incluir un dataset sintético determinístico, generado desde una semilla, con manifest que declare origen `SYNTHETIC`, versión, esquema, generador, hashes por archivo y hash de contenido, y etiquetas esperadas por escenario. El dataset MUST NOT contener números con formato de tarjeta ni datos reales.

#### Scenario: Regeneration
- **WHEN** se regenera el dataset con la misma semilla
- **THEN** los archivos y el manifest son idénticos a los versionados

### Requirement: RF-07 Atomic persistence with audit and outbox

La persistencia SHALL guardar cada observación nueva, su entrada de auditoría y su evento de outbox en una única transacción, serializando escritores concurrentes de la misma clave. Un fallo antes del commit MUST NOT dejar efectos parciales.

#### Scenario: Concurrent duplicates
- **WHEN** varios escritores ingieren simultáneamente la misma observación
- **THEN** existe una sola fila y los demás reciben DUPLICATE

#### Scenario: Rollback
- **WHEN** la transacción falla después de la ingesta
- **THEN** no quedan observación, auditoría ni outbox

### Requirement: RF-08 Versioned migrations and least privilege

El esquema SHALL crearse con migraciones Alembic versionadas ejecutadas por un job separado con el rol de bootstrap, idempotentes al re-ejecutarse y coincidentes con las definiciones SQLAlchemy Core. El rol runtime MUST poder sólo insertar y leer observaciones y auditoría, y MUST NOT poder modificarlas, borrarlas ni crear objetos.

#### Scenario: Re-run migrations
- **WHEN** el job de migración se ejecuta dos veces
- **THEN** ambas ejecuciones terminan con éxito en la misma revisión

#### Scenario: History rewrite attempt
- **WHEN** el rol runtime intenta UPDATE o DELETE sobre observaciones o auditoría
- **THEN** PostgreSQL lo rechaza por privilegios insuficientes
