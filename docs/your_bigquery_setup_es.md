# Primera ejecución en tu BigQuery: SITER A / F.943

Origen: `regulatory-reporting-510011.Transactions.Sample`, ubicación `US`.
Destino de trabajo: `regulatory-reporting-510011.siter_portfolio`, también en `US`.

El 28/09/2026 informaste 1.200 filas y estas columnas: `transaction_id STRING`, `account_id STRING`, `posted_date DATE`, `kind STRING`, `amount_cents INT64`. Son compatibles con la muestra de 1.200 transacciones del repositorio. La ejecución posterior compartida el mismo día confirmó la identidad de contenido y la paridad para agosto de 2026; la evidencia está en `examples/cloud_sample_202608.json`.

## Preparación en Cloud Shell

1. Abrí Google Cloud Console con tu cuenta y el proyecto `regulatory-reporting-510011`. Abrí Cloud Shell.
2. Subí `argentina-regulatory-reporting-pipeline.zip` a Cloud Shell con su opción de cargar archivos.
3. Descomprimí y prepará Python desde la terminal:

```bash
unzip argentina-regulatory-reporting-pipeline.zip
cd finance-regulatory-portfolio
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-bigquery.txt
```

El cliente utiliza Application Default Credentials. Si la sesión no las encuentra, ejecutá `gcloud auth application-default login` y completá el flujo de Google en tu navegador. No pongas credenciales en el repositorio. Tu cuenta necesita crear jobs en el proyecto, leer Sample y crear/actualizar tablas en el dataset de trabajo. El dataset de trabajo debe existir o tu cuenta debe poder crearlo. El proyecto requiere una configuración de API/cuotas/facturación que permita estos jobs.

## Ejecutar la prueba completa

Desde la carpeta `finance-regulatory-portfolio`:

```bash
python3 -m siter.cloud_demo
```

El comando lee `config/bigquery.json` y usa `data/sample` para agosto de 2026. Realiza lo siguiente:

1. Genera el TXT local de referencia y ejecuta sus controles.
2. Comprueba esquema y ubicación de Sample; crea una copia temporal en el dataset de trabajo.
3. Compara una huella SHA-256 del contenido de esa copia con `data/sample/transactions.csv`, conservando duplicados y normalizando fecha/entero. Si el lote no coincide, se detiene antes de cargar tablas auxiliares.
4. Carga automáticamente clientes, cuentas, integrantes, snapshots y plazos fijos del mismo directorio. No necesitás subir esos archivos manualmente a BigQuery.
5. Incorpora la copia verificada como `raw_transactions`, registra el origen y vuelve a comprobar el contenido.
6. Ejecuta el modelo SQL, concilia saldos y genera TXT/ZIP con el exportador común.
7. Compara TXT, ZIP y decisiones por cuenta con la referencia local. Conserva los job IDs y métricas reales.

Las tablas de trabajo se reemplazan en cada ejecución. `Transactions.Sample` solo se usa como origen. No ejecutar dos cargas al mismo tiempo en el mismo dataset de trabajo.

## Resultado que necesitamos revisar

```bash
cat output/cloud_demo/cloud_demo_result.json
```

Compartí ese JSON. El estado esperado es `PASS_LOCAL_BIGQUERY_PARITY_NOT_ARCA_ACCEPTANCE`. Contiene las rutas de los artefactos, hashes, cantidad de cuentas informadas y métricas de BigQuery. `examples/sample_cloud_expected.json` contiene únicamente la referencia local, no evidencia de una ejecución cloud.

Si falla, el resumen guarda estado FAIL y el motivo cuando la falla ocurre en la etapa cloud/paridad. No ignores un error de lote: en ese caso debemos identificar qué CSV se cargó y obtener las dimensiones de ese mismo lote. Errores previos de datos/configuración aparecen directamente en la terminal.

## Comandos individuales opcionales

```bash
python3 -m siter.bigquery --data data/sample --project regulatory-reporting-510011 --dataset siter_portfolio --location US --source-table regulatory-reporting-510011.Transactions.Sample
python3 -m siter.run --data data/sample --period 202608 --out output --engine bigquery --project regulatory-reporting-510011 --dataset siter_portfolio --location US
```

Para otro período de la muestra:

```bash
python3 -m siter.cloud_demo --period 202605
```

## Después de validar la muestra

La siguiente prueba cloud está limitada a 100.000 transacciones y 2.000 cuentas, con sus propias dimensiones y snapshots. Ver `docs/cloud_scale_es.md`. El benchmark de un millón queda como evidencia local, fuera de esta prueba cloud.

Estado: muestra de 1.200 con paridad cloud confirmada por el resultado del usuario; lote de 100.000 validado localmente, ejecución cloud pendiente.
