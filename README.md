# Classical Anomaly Detector Service

Alternativa clásica para el servicio de búsqueda/análisis de anomalías. Expone la misma API `/detect` que el detector cuántico para que el agregador pueda cambiar entre Grover y la búsqueda clásica sin cambiar el contrato.

## Endpoints principales

- `GET /health`: estado del servicio.
- `GET /metrics`: métricas simuladas comparables con la especificación REQ.
- `POST /admin/simulate`: permite simular fallos o degradación.
- `POST /detect`: recibe un lote normalizado y devuelve el índice anómalo.
