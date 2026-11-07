# Memoria y tiempo de TRAIN

## Segunda intervención: motor y ejecución completa

Medido el 7 de noviembre de 2026 en `KPI-6_be-train-performance`, código `8e76ec8`.
**TRAIN completo termina correctamente:** 1.489.931 movimientos, 4.893.888 filas, score oficial **90,39**,
cobertura completa y cero errores de validación. Se conservaron los resultados de los 72 segmentos del evaluador.

| Medida de TRAIN completo | Resultado |
| --- | ---: |
| Tiempo real del comando | 1.346,58 s (22 min 26,6 s) |
| Huella máxima de memoria, incluida compresión de macOS | aproximadamente 7,4 GiB |
| CSV sin comprimir | 211.890.859 bytes |
| Carga | 3,10 s |
| Documentos | 206,40 s |
| Reglas | 143,89 s |
| Resolución, incluidos escritores y creación de casos | 906,49 s |
| Exportación restante | 52,26 s |
| Evaluación oficial | 26,04 s |

El motor conserva las facturas en columnas de Polars e índices de hashes y posiciones compactos, verificando
siempre los campos originales. Busca primero las referencias citadas y solo materializa candidatas abiertas,
emitidas y disponibles. Ya no recorre y reconstruye el histórico completo del tercero en cada movimiento.
Los saldos e historiales usan vectores compactos. La resolución escribe asignaciones y explicaciones por movimiento,
libera propuestas consumidas y exporta el historial por lotes, sin retener todas las filas de entrega en Python.
Los procesos de conciliación y evaluación siguen separados. La API lee progreso explícito durante la resolución.

No ha sido necesario introducir una nueva biblioteca Rust: se utiliza Polars, ya existente, para almacenamiento
columnar y ordenación, y se eliminan materializaciones masivas en Python. La resolución todavía consume unos
15 minutos y es el principal coste restante. No se ha demostrado una aceleración global estable con un A/B
de TRAIN completo: la ejecución histórica se interrumpió después de más de 26 minutos y no tiene tiempo final.

### Cómo se midió la memoria

En macOS, RSS puede bajar al comprimirse páginas y subestimar la presión real. Se consultó `proc_pid_rusage`
con `rusage_info_v4`: `ri_lifetime_max_phys_footprint` incluye la memoria comprimida y conserva el máximo desde
el inicio del proceso. El conciliador registró 7.575,15 MiB; la suma conservadora de los máximos históricos de
los procesos vivos simultáneamente llegó a 7.609,73 MiB (7,43 GiB). El evaluador alcanzó 2.764,88 MiB después
de terminar el conciliador. El árbol de procesos mostró un RSS muestreado de 2.116,69 MiB: no debe confundirse
con la huella completa. Estos datos corresponden a esta máquina y ejecución, no garantizan el mismo máximo
en otras fases o equipos. No se comparan porcentualmente con el RSS histórico.

El comando incluyó un muestreador ligero de pilas del conciliador; los tiempos incluyen ese coste.
Los resultados están en `runs/closebooks-core-train/`; `performance/` contiene el log, las mediciones y el perfil.
El JSON de medición conserva la ruta original de ejecución en `/tmp`, anterior al traslado a `runs/`.
Los datos y artefactos de ejecución permanecen ignorados por Git.

### Paridad y checks del motor

En `mini`, el pico RSS registrado bajó de 879 a 581 MiB respecto a la primera intervención (aproximadamente 34 %).
La última pasada tardó 41,30 s; la anterior, 35,17 s, con variaciones entre pasadas. Esa comparación acredita
la reducción de RSS observada, no una mejora estable de tiempo. La fase `resolve` ahora incluye escribir CSV,
explicaciones y crear casos: sus tiempos no son directamente comparables con los de la primera intervención.

Se compararon todos los artefactos de `mini` contra `d000d76`: mismo CSV y explicaciones, mismos casos,
preguntas y borradores salvo `createdAt`, mismas tablas Parquet con saldos e historial, mismos recuentos,
métricas y los 65 segmentos del evaluador. Score: 87,84 en ambas versiones.
Las nuevas regresiones se vieron fallar antes de implementar índices compactos, historial compacto,
resolución sin acumulación y progreso explícito. También se verifican colisiones de hash e importes de 64 bits.

```text
just be-check: All checks passed!
just be-test: 359 passed, 2 skipped in 61.40s
```

Los omitidos necesitan `db/holdout/` y `db/holdout-drift/`, ausentes en este checkout. Falta comparar todos los
artefactos contra un TRAIN completo de la versión anterior, que no llegó a terminar.

## Primera intervención: medición histórica

Medido el 7 de noviembre de 2026 en `KPI-6_be-train-performance`, comparando el árbol de trabajo con `64d6245`.
Los datos de entrada y el evaluador oficial no se modifican. Esta primera intervención se midió solo en `mini` y `sample`.

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

Las dos últimas líneas documentan la ejecución separada de conciliación y evaluación.

## Trabajo pendiente

La resolución sigue siendo el principal coste de TRAIN. Queda reducir sus búsquedas y bucles de Python a partir
del perfil guardado, manteniendo la paridad. La caché persistente de parsers queda para otro cambio.
