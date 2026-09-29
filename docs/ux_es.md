# Consola de reporting SITER A

## Workspace de ejecución v1

La consola ahora incluye carga de CSV anonimizados, autenticación, validación previa, configuración, ejecución en segundo plano y resultados por usuario. Para iniciarla: `python3 -m siter.server add-user analyst` y `python3 -m siter.server serve`; abrir `http://127.0.0.1:8000`. Ver [guía de ejecución](execution_console.md) y [contrato CSV](csv_contract.md). La importación opcional desde BigQuery lee fuentes autorizadas y procesa localmente; no ejecuta el modelo SQL desde la UX.

## Referencia estática original

La consola está incluida en `web/`. Para abrirla localmente, ejecutar `python3 -m http.server 8000 --directory web` desde la raíz del repositorio y visitar `http://localhost:8000`. El README incluye capturas; la demo pública está pendiente.

## Alcance

Interfaz estática con resultados guardados de la muestra de 1.200 transacciones. No ejecuta SQL, no necesita claves y no se conecta a BigQuery. La validación cloud documentada corresponde al reporte de agosto sobre la muestra de 1.200 transacciones.

- Resumen: población informada, movimientos del mes, conciliación, registros y motivos de inclusión.
- Cuentas: búsqueda, filtro de selección, paginación y detalle de importes/motivos.
- Controles: conciliación, validación del TXT, paridad y procedencia de la evidencia.
- Inspector TXT: selección de registro y campo, posiciones exactas y bytes originales descargables.
- Historial: seis cierres locales, agosto identificado con evidencia adicional cloud.

Las descargas son reproducciones locales. Los hashes TXT y ZIP de agosto coinciden con el resumen de la ejecución en BigQuery. La auditoría local y el resumen cloud se descargan por separado. No se presentan meses locales como validados en cloud ni se simula una transmisión ante ARCA.

## Reproducir datos

```bash
python3 -m scripts.export_ux --out web/data
```

Esto regenera los seis cierres desde `data/sample`, copia TXT/ZIP/auditorías y construye `reporting.json` con decisiones, registros y layout. No hace llamadas de red. El frontend HTML/CSS/JavaScript y sus assets están incluidos en `web/`.

## Recorrido de revisión

1. Abrir agosto: 200 movimientos mensuales, 4 cuentas informadas y diferencia cero.
2. Abrir una cuenta para relacionar sus importes con sus motivos de inclusión.
3. Ver Controles: comprobar la distinción entre validación local, paridad cloud y aceptación por ARCA.
4. Abrir el inspector, elegir un registro 02 y seleccionar el campo saldo o acreditaciones.
5. Descargar el TXT o ZIP y contrastar su hash con la evidencia.
6. Cambiar a otro mes y confirmar que solo figura validación local.

## Presentación

La consola se puede revisar mediante las capturas del README o ejecutándola localmente. La publicación de una demo accesible sin permisos está pendiente. La consola muestra resultados guardados y no ejecuta consultas cloud.

## Validación de esta entrega

Verificados: sintaxis JavaScript, existencia de descargas de seis meses, hashes, cantidades de cuentas y registros, y posiciones del inspector. Las 21 pruebas del pipeline pasan. Se revisaron en navegador las vistas de resumen, controles e inspector, y se capturaron para el README. No se realizó validación nativa WebMCP.
