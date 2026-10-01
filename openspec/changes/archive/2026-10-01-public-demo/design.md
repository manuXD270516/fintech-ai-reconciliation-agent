## Context

Implementa M10 de [docs/09-roadmap.md](../../../../docs/09-roadmap.md) con D10 de [docs/11-implementation-decisions.md](../../../../docs/11-implementation-decisions.md). [docs/08-risks.md](../../../../docs/08-risks.md) exige revisar secretos, licencias y datos, aislar las sesiones de demo, tener un kill switch de IA y mantener disponible la ruta determinística.

## Decisions

- **Aislamiento por tenant.** La API toma el tenant del token, así que una sesión es un tenant `demo-<id>` con sus propios tokens de desarrollo. No hace falta otra infraestructura. Los IDs de lote se repiten entre sesiones sin colisionar.
- **Kill switch en la API.** El switch se comprueba en `POST …/investigations` después de la autorización, para no revelar el estado a quien no tiene permiso. No apaga el proceso investigador: las investigaciones ya pedidas terminan. Cambiarlo implica recrear el contenedor `api` (`scripts/demo.py kill-switch`), y `/metrics` lo refleja.
- **Resultados escritos a mano y enlazados.** Cada cifra del documento sale de un archivo de evidencia enlazado. Un generador automático no aportaba más que copiar valores, y la sanitización la garantizan los pasos `policy` y `secrets`.
- **Rutas personales.** Se redactaron en el árbol actual (`C:\Users\<user>`) y `policy` lo vigila. No se reescribió la historia: queda como decisión del propietario antes de publicar.
- **Licencias.** El inventario es offline: metadatos instalados de Python y el campo `license` de los `package-lock.json`. No se elige licencia para el repositorio.

## Risks / Trade-offs

- `results.md` puede quedar desactualizado si cambia la evidencia. Cada fila enlaza su fuente, y el gate de cierre se ejecuta después de escribirlo.
- El drill del kill switch recrea el contenedor `api` dos veces dentro del smoke, lo que suma unos segundos.
