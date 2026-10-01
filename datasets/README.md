# Ficha de datasets

Todos los datos de este repositorio son **sintéticos**: proveedores, comercios, montos, documentos e incidentes ficticios. No contienen personas, PAN, CVV, credenciales ni datos de clientes. Cada dataset tiene un `manifest.json` con versión, semilla o generador, conteos y el hash SHA-256 de cada archivo. Los tests y las evaluaciones verifican esos hashes.

| Dataset | Versión | Origen | Contenido | Uso |
|---|---|---|---|---|
| `synthetic/transactions-v2` | v2 (semilla 20260929, `synthetic-transactions/v2`) | Generador del repo (`scripts/generate_synthetic.py`) | 44 pagos de 2 proveedores ficticios (`prov-alfa`, `prov-beta`): 44 filas de ledger interno y 48 de reporte del proveedor, con etiquetas (`expected_match`, `expected_discrepancies`) | Smoke, demo (`scripts/demo.py seed`), E2E del dashboard |
| `synthetic/transactions-v1` | v1 | Igual | Mismos archivos de origen con las etiquetas v1, que v2 corrige | Historia (M1); no se usa en gates |
| `synthetic/knowledge-v1` | v1 | Corpus escrito a mano | 17 documentos ES/EN versionados (guías de liquidación, códigos de error, incidentes, runbooks, procedimientos y un documento de otro tenant) y 38 queries etiquetadas con split `dev`/`holdout` | Retrieval híbrido (M3), MCP (M4), evaluación |
| `synthetic/provider-status-v1` | v1 | Escrito a mano | 6 snapshots de estado de plataforma por proveedor, con dos incidentes ficticios | Tool `get_provider_status` |
| *(en memoria)* | `recon_domain.synthetic.generate`, semilla 20261001 | Generador | 1210 pagos (11 escenarios × 110) en 121 familias, con split 60/20/20 por familia | Suite `reconciliation` de `recon_evals` (M7) |

**Escenarios de `transactions-v2`:** 4 pagos por cada uno de `exact`, `amount_mismatch`, `status_mismatch`, `duplicate_external`, `missing_external`, `missing_internal`, `weak_reference`, `unknown_status`, `invalid_precision`, `revision_out_of_order` y `transport_replay`.

**Separación del oráculo:** las etiquetas las escribe el generador, independiente del motor `rules/v1`. Sólo se usan para puntuar resultados y para derivar el alcance de los lotes (tenant, proveedor y cuenta), nunca para decidir resultados.

**Limitaciones:**
- Los datos son pequeños y regulares a propósito. Una accuracy de 1.0 sobre ellos **no** demuestra generalización a datos reales.
- El corpus de conocimiento es breve, y los embeddings son de hashing (no semánticos).

**Licencia:** los datasets se crearon para este repositorio. El repositorio todavía no declara una licencia; es una decisión pendiente del propietario.
