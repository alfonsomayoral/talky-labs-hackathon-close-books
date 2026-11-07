# Primera reducción de memoria de TRAIN

Medido el 7 de noviembre de 2026 en `KPI-6_be-train-performance`, comparando el árbol de trabajo con `64d6245`.
Los datos de entrada y el evaluador oficial no se modifican. No se ha ejecutado TRAIN completo con estos cambios.

## Cambios

- CSV y JSONL se serializan mientras se escriben. Los gzip usan un buffer de 1 MiB y conservan cabecera determinista.
- Los saldos y totales se guardan como enteros de 64 bits. Resolución y condiciones comparten el índice de partidas;
  divisas, terceros, fechas y condiciones usan etiquetas compartidas y códigos enteros de 32 bits.
- El historial guarda tuplas y recupera los campos JSON del contrato al exportarse.
- Una fase con golden termina su proceso de conciliación antes de que el coordinador cargue el evaluador.
  `--no-score` permite escribir los artefactos sin evaluar.
- La comparación de prefijos usa `rapidfuzz.distance.Prefix.similarity`, dependencia ya instalada, con el mismo
  criterio de coincidencia. No introduce casación aproximada.

## Mediciones sin perfilador

`mini`: 57.483 movimientos, 183.372 filas de entrega y 559.366 partidas en el estado exportado.

| Medida | Antes | Versión final |
| --- | ---: | ---: |
| Tiempo real del comando con `/usr/bin/time -l` | 60,24 s | 35,17 s |
| Pico RSS reportado por ese comando | 995 MiB | 879 MiB |
| Resolución, incluida construcción del motor y liberación | 14,67 s | 12,82 s |
| Salidas | 5,00 s | 3,54 s |
| Score oficial | 87,84 | 87,84 |

El descenso observado del pico RSS es del 11,6 %. Los tiempos varían: una primera pasada anterior dio 41,29 s,
y una comparación aislada del motor dio 11,26/12,78 s antes y 10,06/17,06 s después. No se afirma una aceleración
global estable a partir de estas pasadas. La extracción de documentos también osciló de 14,56 a 34,17 s.
El valor `peakRssMb.score` final es 221 MiB en el coordinador; es otro proceso y no incluye los workers de documentos.

Prueba aislada del escritor: 5.000 explicaciones con una referencia larga en Unicode, compartida en la entrada.
El máximo de asignaciones de Python medido con `tracemalloc` pasó de **351,2 MiB a 1,37 MiB**.
Esta cifra corresponde al escritor, no al pipeline completo. Los tests limitan ese pico a 4 MiB y comprueban
que se conservan todas las filas y el texto Unicode.

## Paridad y checks

Primero se vieron fallar seis regresiones: los tres escritores por exceso de memoria, la construcción del estado
por columnas y las dos rutas de ejecución sin solapar conciliación y evaluación. Después se implementaron los cambios.

Comparación de `mini` contra la ejecución anterior:

- CSV y explicaciones: mismo SHA-256 del contenido descomprimido.
- Casos, preguntas y borradores: mismos registros, excluyendo `createdAt`.
- Los tres Parquet de hechos y estado: mismas tablas, incluidos saldo final e historial de cada partida.
- Mismos recuentos, métricas y resultados en los 65 segmentos del evaluador oficial.

La versión final también conserva todos esos artefactos y los 65 segmentos de `sample` (score 85,32).

Salida final de los checks:

```text
just be-check: All checks passed!
just be-test: 354 passed, 2 skipped in 58.90s
```

Los dos tests omitidos necesitan `db/holdout/` y `db/holdout-drift/`, no disponibles en este checkout.

Comandos de comprobación:

```bash
just be-check
just be-test
cd backend
uv run closebooks run --phase mini --out ../runs/performance-mini
uv run closebooks run --phase train --out ../runs/train-mem --no-score
uv run closebooks score ../runs/train-mem
```

Las dos últimas líneas documentan cómo ejecutar TRAIN; no son una ejecución realizada en esta revisión.

## Trabajo pendiente

El motor todavía construye índices completos de terceros y referencias y conserva las filas resueltas en memoria.
La exportación del historial a Parquet también materializa todos sus registros. La siguiente reducción debe atacar
esas estructuras y la búsqueda repetida sobre facturas históricas. Falta medir TRAIN completo y verificar el objetivo
de menos de 8 GB; las cifras de `mini` no garantizan ese límite. La caché persistente de parsers queda para otro cambio.
