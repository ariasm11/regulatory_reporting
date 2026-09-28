# Demo de entrevista: tres minutos

## 0:00–0:30 · Problema y alcance

Mostrar el resumen de agosto. Explicar que el objetivo es traducir requisitos de SITER A / F.943 en un flujo reproducible de datos, decisiones y archivo de ancho fijo. La muestra es sintética: 1.200 transacciones en seis meses y 50 cuentas.

## 0:30–1:15 · Regla de negocio y trazabilidad

Abrir una cuenta informada y explicar sus motivos de inclusión. Mostrar dónde se calculan sus métricas en `sql/monthly.sql` y dónde se parametrizan umbrales/cortes en `config/reporting.json`. Distinguir movimientos del mes de saldo al último día hábil. Señalar las limitaciones del escenario y las decisiones que requerirían acuerdo con Reporting.

## 1:15–2:00 · Calidad y archivo

Abrir Controles: la conciliación da cero. Abrir Inspector TXT, seleccionar un registro 02 y un campo de importe. Mostrar posición, longitud y representación en pesos enteros frente al origen en centavos. Descargar el archivo y explicar que un lector independiente valida su estructura y totales.

## 2:00–2:40 · Evidencia cloud

Mostrar el resumen de la ejecución BigQuery de agosto y su paridad con el motor local: mismo TXT, ZIP y decisiones por cuenta. Conservar la distinción entre evidencia compartida por el usuario, reproducción local y aceptación de ARCA. Los otros cinco meses solo tienen evidencia local. El benchmark de un millón también es local; no presentarlo como capacidad cloud probada.

## 2:40–3:00 · Criterio operativo

Explicar la separación entre el pipeline y la interfaz: la consola usa resultados guardados, por lo que navegar o descargar no lanza queries. Cerrar con las mejoras necesarias para producción: lotes inmutables, ejecución concurrente controlada, revisión regulatoria del alcance y observabilidad de errores/costos.

## Evidencia complementaria

Mostrar en el repositorio un test de duplicado, uno de diferencia contra el saldo fuente y el corte de mayo. No afirmar ahorros, tiempos de producción, aceptación fiscal o capacidad de Revolut que el proyecto no haya medido.
