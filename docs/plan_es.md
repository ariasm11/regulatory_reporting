# Estado y próximos pasos del proyecto

## Hitos cerrados

- Motor Python y modelo SQL de SITER A / F.943 para el alcance documentado.
- Exportador TXT, ZIP y lector independiente, conciliaciones y 21 pruebas locales.
- Muestra sintética de 1.200 transacciones y 50 cuentas, seis meses.
- Validación cloud de agosto: ejecución compartida por el usuario, identidad del lote y paridad TXT/ZIP/decisiones confirmadas, diferencia de conciliación cero. El usuario acepta esta evidencia como cierre de la etapa cloud.
- Benchmark local de un millón; no presentar como prueba cloud.
- Lote opcional de 100.000 generado y validado localmente. Su ejecución cloud no es requerida.
- Consola UX de resultados guardados: resumen, cuentas, controles, inspector y seis períodos. Sin conexión a BigQuery.

## Próximos pasos

1. Revisar la demo privada: seleccionar agosto, abrir una cuenta informada, revisar controles, inspeccionar un campo y descargar TXT.
2. Publicar y revisar el repositorio `ariasm11/regulatory_reporting`. Conservar generador, muestra, SQL, pruebas, evidencia y documentación; excluir credenciales y grandes datasets.
3. El código de la consola se incluye en `web/` y su demo está versionada por Sites; la URL privada no será accesible a reclutadores sin cambiar su acceso.
4. Mantener la trazabilidad entre reglas de inclusión, cálculos SQL, posiciones del TXT y controles de calidad.

## Alcance futuro, no bloqueante

Extender escenarios regulatorios solo con reglas y fuentes confirmadas: varias cuentas por titular, cotitulares, monedas extranjeras, correcciones y registros fuera de 01–05. Las decisiones normativas señaladas en specification.md siguen requiriendo revisión antes de cualquier uso real.

La evidencia de esta demo demuestra consistencia del pipeline, no aceptación por ARCA ni capacidad de producción de Revolut.
