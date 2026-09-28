# Prueba cloud opcional limitada a 100.000 transacciones

La validación cloud se cerró con la muestra de 1.200 por decisión del usuario. Esta prueba es opcional, no un requisito ni el siguiente paso del proyecto.

Decisión del usuario: reducir el volumen para controlar la exposición a costos. Esta versión usa 100.000 como tope efectivo del comando `scripts.cloud_scale`.

## Lote

- 100.000 transacciones totales, distribuidas entre marzo y agosto de 2026.
- 2.000 clientes y 2.000 cuentas, con dimensiones, integrantes, plazos fijos y snapshots propios.
- Aproximadamente 6,95 MB de archivos locales, sin equipararlos al almacenamiento o procesamiento facturable en BigQuery.
- Dataset de trabajo: `regulatory-reporting-510011.siter_trial_100k`, ubicación US.
- Primera ejecución: agosto. La carga contiene seis meses, pero el reporte inicial corresponde a uno.

El CSV se cuenta antes de iniciar cualquier conexión cloud. Si supera 100.000 filas, el comando se detiene aunque el manifiesto declare otra cantidad. El control también se aplica a `--data`. No existe una opción para subir ese límite en este comando.

## Ejecutar desde Cloud Shell

Usar la versión actualizada del ZIP. Desde la raíz del proyecto y con el entorno Python activo:

```bash
python3 -m scripts.cloud_scale
cat output/cloud_trial_100k/cloud_scale_result.json
```

El ZIP incluye `data/trial_100k` con todas sus fuentes auxiliares. Desde un clon GitHub, generarlas antes:

```bash
python3 -m siter.generate --out data/trial_100k --transactions 100000 --customers 2000
```

El script carga todas las fuentes del lote y compara TXT, ZIP y decisiones por cuenta entre el motor local y BigQuery. Conserva los job IDs, bytes procesados, consumo de slots y tiempos completos en el resultado. Las tablas de trabajo del trial se reemplazan en ejecuciones posteriores; no correr cargas concurrentes.

La referencia local está en `examples/trial_100k_expected.json`: para agosto informa 249 cuentas, 34 integrantes de cuentas y 39 plazos fijos, más la cabecera. La aceptación cloud todavía está pendiente. Los TXT son sintéticos y no deben presentarse ante ARCA.

## Alcance del control de costos

Reducir filas no garantiza costo cero. El tope de filas es local a este comando; no modifica cuotas ni facturación de Google Cloud, ni limita otros comandos del repositorio. Las consultas principales conservan el límite existente de 20 GB por job; las consultas auxiliares no tienen un límite explícito. No hay un presupuesto total automático ni una estimación completa de bytes facturados. Los tiempos completos incluyen controles y exportación.

El millón de transacciones permanece disponible para el benchmark local, pero este comando lo rechaza. La muestra original de 1.200 y su ejecución cloud siguen documentadas por separado.
