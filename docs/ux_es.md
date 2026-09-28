# Consola de reporting SITER A

Demo privada: https://siter-reporting-console.ariasmatias91.chatgpt.site

Despliegue publicado el 28/09/2026. Fuente versionada por Sites; sitio `appgprj_6aba75b35b8481918f1fd27abdd3462c`.

## Alcance

Interfaz estática con resultados guardados de la muestra de 1.200 transacciones. No ejecuta SQL, no necesita claves y no se conecta a BigQuery. La etapa cloud queda cerrada sobre la validación de agosto aceptada por el usuario.

- Resumen: población informada, movimientos del mes, conciliación, registros y motivos de inclusión.
- Cuentas: búsqueda, filtro de selección, paginación y detalle de importes/motivos.
- Controles: conciliación, validación del TXT, paridad y procedencia de la evidencia.
- Inspector TXT: selección de registro y campo, posiciones exactas y bytes originales descargables.
- Historial: seis cierres locales, agosto identificado con evidencia adicional cloud.

Las descargas son reproducciones locales. Los hashes TXT y ZIP de agosto coinciden con el resultado cloud compartido por el usuario. La auditoría local y el resumen cloud se descargan por separado. No se presentan meses locales como validados en cloud ni se simula una transmisión ante ARCA.

## Reproducir datos

```bash
python3 -m scripts.export_ux --out web/data
```

Esto regenera los seis cierres desde `data/sample`, copia TXT/ZIP/auditorías y construye `reporting.json` con decisiones, registros y layout. No hace llamadas de red. El frontend HTML/CSS/JavaScript y sus assets están incluidos en `web/` y también se conservan en el repositorio del Site; la URL publicada figura al inicio de este documento.

## Recorrido de revisión

1. Abrir agosto: 200 movimientos mensuales, 4 cuentas informadas y diferencia cero.
2. Abrir una cuenta para relacionar sus importes con sus motivos de inclusión.
3. Ver Controles: comprobar la distinción entre validación local, paridad cloud y aceptación por ARCA.
4. Abrir el inspector, elegir un registro 02 y seleccionar el campo saldo o acreditaciones.
5. Descargar el TXT o ZIP y contrastar su hash con la evidencia.
6. Cambiar a otro mes y confirmar que solo figura validación local.

## Presentación

La demo comienza privada. Para compartirla con reclutadores habrá que habilitar el acceso apropiado; no cambiarlo sin indicación del usuario. Repositorio de destino: https://github.com/ariasm11/regulatory_reporting. La consola no integra un botón de ejecución cloud para evitar consultas accidentales.

## Validación de esta entrega

Verificados: sintaxis JavaScript, existencia de descargas de seis meses, hashes, cantidades de cuentas y registros, y posiciones del inspector. Las 21 pruebas del pipeline pasan. No se realizó QA visual en un navegador ni validación nativa WebMCP; revisar la interfaz antes de compartirla externamente.
