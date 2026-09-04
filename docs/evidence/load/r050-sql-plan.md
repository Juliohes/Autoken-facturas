# Evidencia SQL de R-050

Medición realizada contra el Postgres real del stack el 26/08/2026, usando valores sintéticos y el
rol administrador únicamente para inspeccionar el plan. No contiene identificadores de tenants,
usuarios, facturas ni hashes reales.

## Índices relevantes

- `uploaded_files_company_uploader_sha256_unique`: `(company_id, uploaded_by, sha256)`.
- `uploaded_file_pages_company_uploader_sha256_unique`: `(company_id, uploaded_by, sha256)`.

## Resultado

La búsqueda de duplicado en `uploaded_files` tuvo una ejecución de `0,03 ms`. La búsqueda combinada
de raíz y páginas tuvo una ejecución de `0,09 ms`. La tabla tenía 53 filas de raíz y ninguna página;
el plan mostró el índice único de páginas y un scan secuencial de la raíz por su tamaño reducido.

Conclusión: no se añade un índice ni se reescribe el SQL sin evidencia adicional. El margen restante
del p95 HTTP de R-050 no está en estas consultas medidas.
