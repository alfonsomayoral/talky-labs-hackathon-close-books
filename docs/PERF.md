# PERF.md: tiempo y memoria del pipeline

Análisis medido el 7 nov 2026 sobre el commit `64d6245`. No cambia código: todo lo que se prueba aquí se aplicó en memoria, desde un script externo.

## 1. Conclusión

- **FINAL no corre riesgo por tiempo.** Holdout (199.987 movimientos) tarda 136 s; FINAL (~220 k) saldría en ~150 s (estimado), muy por debajo de los 15 min. **El riesgo es la memoria:** 7,3 GB del run más 3,9 GB de `serve`, en un Mac que ya se reinició dos veces.
- **Cuatro cambios pequeños, ya probados en holdout, dan casi todo:**

| | Hoy | Con los cambios | CSV |
| --- | --- | --- | --- |
| Run de holdout | 136 s, 7,3 GB | **105 s, 5,06 GB** | idéntico con `cmp` |
| Arranque de `serve` | 52 s, 3,9 GB | **4,8 s, 2,4 GB** | no le afecta |

- **Medido ya en el código, las tres ramas juntas:** 118,5 s; 5,80 GB de RSS y 5,76 GB de `peak memory footprint` (hoy, 7,12 GB). Los 5,06 GB de la tabla son RSS de un run con el mismo footprint, 5,76 GB: el RSS de macOS varía con la presión de memoria, así que para comparar sirve mejor el footprint.
- **Hoy:** la fase 1 (§7), unas 2 h con verificación. **No hoy:** Rust ni particionar por sociedad.
- **Aviso:** no lances TRAIN completo antes de arreglar `write_explanations`. Solo esa lista pediría ~21 GB (extrapolado de 4 KB por fila y 5,4 M de filas; TRAIN nunca ha llegado a esa etapa).

## 2. Cómo se midió

Máquina: Mac de 24 GB, 18 núcleos (6 de rendimiento, 12 de eficiencia), con un `serve` de demo inactivo en `:8000` y los builds del frontend en pausa.

- **Tiempo y pico:** `/usr/bin/time -l`, que da el pico del mayor proceso, no la suma. La suma del árbol de procesos se muestreó cada 2 s con `ps`.
- **Por etapa:** `stages` y `peakRssMb` de `run.json`.
- **Funciones:** cProfile, que infla `resolve` ×3,3 (228 s frente a 69 s). Por eso los tiempos del motor salen de sondas con `perf_counter`, que añaden ~8 %. py-spy no está instalado.
- **Línea base para `cmp`:** se conservan `runs/perf-holdout-a` y `runs/perf-sample-a`.

| Fichero de la línea base | sha256 (inicio) |
| --- | --- |
| `perf-holdout-a/submission.csv.gz` | `27bb41eac2d04e1e` |
| `perf-holdout-a/explanations.jsonl.gz` | `26bb9355da4a8571` |
| `perf-sample-a/submission.csv.gz` | `6922ea0dc06596b8` |

**Una contaminación conocida:** durante los primeros segundos de la medida sin perfilador corrió un `sample` de prueba con `nice 20`. El resultado (136 s) cuadra con los 137–138 s anteriores.

## 3. Mapa del pipeline

Holdout: 2.326.290 partidas en memoria (incluye 400 días de TRAIN), 680.246 filas.

| Etapa | Qué hace | Dónde | Motor | Se queda en memoria |
| --- | --- | --- | --- | --- |
| `load` | CSV a tablas, todo como texto; céntimos; EUR por `join_asof` | `load.py:200` `load_phase` | Polars, con `read_csv` entero | `items` 275 MB, `txns` 53 MB. El RSS queda en 1,8 GB: lo demás lo retiene el asignador |
| `documents` | 6.763 avisos y 59.273 PDFs a hechos | `documents/advices.py:332`, `documents/pdfs.py:318` | Python puro (pypdf, openpyxl, regex) en un pool `spawn` de 6 procesos | `AdviceBatch` (`lru_cache`), `PdfFacts` (`_CACHE`) |
| `rules` | Seis pasadas proponen por movimiento | `rules/__init__.py:19` | Joins de Polars y después `iter_rows` en Python (`payment_runs.py:93`, `advices.py:63`) | 86.542 propuestas con 502.900 líneas |
| `index` | Índices del motor (cuenta dentro de `resolve`) | `party_amount.py:164` `reindex`, `parties.py:32` | Python puro: dicts de tuplas de 9 campos | 2,3 M de entradas, +2,1 GB de RSS (918 B por entrada) |
| `resolve` | Bucle por fecha: propuesta o motor, política, saldo | `resolve.py:11`, `party_amount.py:181`, `policy.py`, `state.py` | Python puro | Saldo e historia por partida, 680 k `Row` |
| `output` | CSV, explicaciones, casos, hechos, estado | `output.py`, `cases.py`, `drafts.py` | Python y gzip; Polars para el parquet | Lista de resultados de `orjson` |
| `score` | Evaluador oficial | `evaluate.py:39` | Python | Golden |
| `serve` | Tablas DuckDB en memoria y listados de ficheros | `api/store.py:56`, `api/run_data.py:72`, `api/phase_data.py` | DuckDB | Tablas ~1 GB según DuckDB |

## 4. Medidas

### 4.1 Por fase

| Fase | Movimientos | Filas | Tiempo real | CPU | Pico mayor proceso | Pico árbol |
| --- | --- | --- | --- | --- | --- | --- |
| sample | 8.499 | 30.146 | 9,7 s | 20,7 s | 0,58 GB | no muestreado |
| holdout | 199.987 | 680.246 | 136 s | 356 s | 7,3 GB | 6,7 GB (muestreo cada 2 s, no ve el pico) |

### 4.2 Holdout por etapa

| Etapa | Tiempo | Pico acumulado | Nota |
| --- | --- | --- | --- |
| `load` | 1,7 s | 2,7 GB | Pico transitorio; después baja a 1,8 GB |
| `documents` | 44,7 s | 2,7 GB | Avisos 4,2 s, PDFs 42,5 s. Los 6 workers suman ~0,73 GB |
| `rules` | 8,4 s | 3,1 GB | `payment_runs` 2,2; `advices` 2,1; `dd_batches` 1,5; `categories` 1,5; cheques 0,5; tarjetas 0,4 |
| `resolve` | 68,7 s | 5,1 GB | Construir índices 6,4 s; motor unos 58 s |
| `output` | 8,9 s | **7,0 GB** | `write_explanations` 2,1 s y +2,2 GB; `write_open_items` 2,3 s |
| `score` | 2,9 s | 7,0 GB | |

Con sondas: 147 s y 7,4 GB. Con cProfile: 307 s y 6,8 GB. Los tres CSV son idénticos.

### 4.3 El motor (sondas, holdout)

113.445 movimientos llegan al motor; `_match` se llama 261.368 veces.

| Pieza | Llamadas | Tiempo | Entrada |
| --- | --- | --- | --- |
| `_match` (incluye lo de abajo salvo `find`) | 261.368 | 52,8 s | |
| `_cited` | 236.419 | **25,9 s** | 15,6 M de partidas, ~66 por llamada |
| `find` | 113.445 | 7,2 s | |
| `_subset` | 138.271 | 3,4 s | 1,4 M |
| `_small_subset` (dentro de `_subset`) | 14.911 | 1,8 s | 342 k |
| `_tokens` | 250.168 | 1,7 s | |
| `_short_paid` | 141.252 | 1,0 s | |
| `_consecutive` | 123.033 | 1,0 s | 860 k |

El coste por movimiento sube con el histórico visible: de 2,4 s a 3,4 s cada 5.000 llamadas entre enero y junio.

### 4.4 Las 15 funciones más calientes (cProfile, holdout, tiempo propio)

Sin contar la espera a los workers (`select.poll`, 41,9 s).

| # | Función | Llamadas | Tiempo propio |
| --- | --- | --- | --- |
| 1 | `party_amount.py:270 _cited` | 236.419 | 85,9 s |
| 2 | `str.lstrip` | 208,6 M | 15,7 s |
| 3 | `str.isdigit` | 208,8 M | 15,0 s |
| 4 | `str.startswith` | 132,0 M | 13,9 s |
| 5 | `len` | 241,8 M | 11,7 s |
| 6 | `state.py:15 OpenBalances.open` | 18,8 M | 10,7 s |
| 7 | `party_amount.py:234 _match` | 261.368 | 10,4 s |
| 8 | `PyLazyFrame.collect` | 1.736 | 6,0 s |
| 9 | `party_amount.py:164 reindex` | 1 | 5,5 s |
| 10 | `str.endswith` | 46,0 M | 5,3 s |
| 11 | `dict.get` | 21,6 M | 4,0 s |
| 12 | `re.Pattern.sub` | 11,4 M | 3,9 s |
| 13 | `parties.py:118 _common_prefix` | 7,4 M | 3,8 s |
| 14 | `parties.py:89 _in_text` | 67.185 | 3,7 s |
| 15 | `resolve.py:11 resolve` | 1 | 3,7 s |

Los números 2 a 5 y 10 salen casi todos de `_cited`. En `sample` manda `find`, no `_cited`, porque sus terceros tienen pocas partidas: `sample` no sirve para decidir qué optimizar.

### 4.5 Arranque de `serve`

Acepta conexiones a los 53 s, con 3,7–3,9 GB. Una sentencia se lleva casi todo:

| Paso | Tiempo |
| --- | --- |
| **`CREATE TABLE rows`** (`run_data.py:104`) | **46,2 s** |
| `CREATE TABLE asg`, `bank`, `cases`, `tx` | 1,3 s entre todas |
| `accounts`, `ensure_items`, `documents`, `detail_files` | 2,3 s |
| Importar módulos | 0,9 s |

Esa sentencia, descompuesta y sobre tablas ya materializadas:

| Variante | Tiempo |
| --- | --- |
| Original: `read_json` dentro del join con `row_number` y `ASOF` | 45,8–47,2 s |
| `read_json` a una tabla con `row_number` | 0,63 s |
| El mismo join sobre esa tabla | 0,11 s |
| El mismo join sobre un parquet de las explicaciones (9 MB) | 0,12 s |

## 5. Diagnóstico

### 5.1 Por qué `serve` tarda un minuto

**Dato:** el plan de la sentencia original estima ~45 filas para `read_json`, que trae 680.246, y resuelve el `ASOF` con un `Hash Group By` y `arg_max`. Materializar primero da las mismas 680.246 filas, sin diferencias por `rowNo` en `bankTxnId`, `itemId`, `amountEur`, `entity` ni `sources`, en 0,74 s.

**Inferencia:** con tan pocas filas estimadas, DuckDB elige la variante de `ASOF` para entradas pequeñas. No lo he confirmado en su código.

No es el JSON, el gzip ni el tamaño de las tablas. Los 1,5 GB de RSS que desaparecen eran memoria de ese plan.

### 5.2 Por qué el run pica en 7 GB

| Hipótesis | Veredicto | Evidencia |
| --- | --- | --- |
| Lista de `orjson` | **Sí, el pico** | Prueba aislada, 680 k líneas: 2.674 MB de RSS para 152 MB de datos; copiando cada resultado, 183 MB. Son ~4 KB retenidos por fila. **Inferencia:** `orjson` reserva un búfer y no lo devuelve al encoger |
| Índices en diccionarios | **Sí, la meseta** | +2,1 GB al construirlos; es lo que queda como pico al quitar la lista (5,6 GB). Crecen con las partidas |
| Asignador de Polars | **Sí** | Tras `load`, 1,8 GB de RSS para 328 MB de tablas. Con `_RJEM_MALLOC_CONF=dirty_decay_ms:0,muzzy_decay_ms:0`: 950 MB de RSS y 2,13 GB de pico |
| Pools que duplican memoria | **No** | 6 workers suman 0,73 GB; 10 workers, ~1,2 GB. Y actúan antes del pico |
| Copias de DataFrames | **Menor** | `_known` copia ~275 MB (`party_amount.py:153`) |

### 5.3 Por qué TRAIN no escala

**Dato:** cada llamada a `_match` recorre todas las partidas de su tercero (`party_amount.py:236`), y `_cited` cruza cada partida visible con cada token (~13 por partida). Las partidas cerradas no se pueden quitar: una cita a una factura ya pagada es lo que detecta un duplicado. Por eso el coste crece con el histórico de cada tercero.

**Estimación del motor en TRAIN:**

| Modelo | Holdout | TRAIN | Factor |
| --- | --- | --- | --- |
| Llamadas (una por partida, TRAIN con DuckDB) | 782 k | 5,64 M | ×7,2 |
| Partidas recorridas | 1.550 M | 15.828 M | **×10,2** |

Aplicado a los ~60 s del motor en holdout, salen **10–12 min**. La extrapolación de la subida de §4.3 da unos 12 min.

**Lo que no sé:** eso no explica por sí solo que TRAIN siguiera sin acabar a los 26 min. Es superlineal, pero poco: ×10 frente a ×7. Faltan por medir, porque aquel run se paró sin dejar `run.json`:

- `_subset` y `_consecutive` con más partidas abiertas: en TRAIN nada las cierra si se pagaron antes de sus datos.
- Las pasadas de `rules` con 5,6 M de partidas.
- La presión de memoria: a 12,8 GB con otras cargas, el compresor pudo frenarlo todo.

**Memoria en TRAIN (extrapolado):** índices ~5 GB (918 B × 5,6 M) y lista de `orjson` ~21 GB (4 KB × 5,4 M). Esa lista basta para volver a saturar el Mac.

Para FINAL esto no importa: su tamaño es el de LIVE y sus partidas previas están acotadas a 400 días. TRAIN solo hace falta para puntuar contra su golden, y holdout ya lo cubre.

### 5.4 Un hallazgo aparte

`open_items.parquet` cambia de orden entre dos runs del mismo código: ~250 de 1.036.499 filas. Viene de `unique("item_id", keep="last")` sin `maintain_order` (`load.py:187`). El CSV salió idéntico en las 5 ejecuciones de holdout, y CONTRACT §3 solo promete el CSV, pero el orden llega a las listas del motor. **Inferencia:** las decisiones no dependen de él, porque el motor ordena antes de elegir. No lo he demostrado.

## 6. Opciones

Beneficios sobre holdout. «Medido» es una ejecución real con el cambio aplicado en memoria.

### (a) Vectorizar en Polars y DuckDB

| Cambio | Beneficio | Coste | Riesgo | Verificación |
| --- | --- | --- | --- | --- |
| **Partir `CREATE TABLE rows` en dos** | **Medido:** `serve` 52 → 4,8 s; 3,9 → 2,4 GB | 15 min | Muy bajo | `rows` igual por `rowNo` (hecho en 5 columnas; faltaría el resto) |
| **`_cited` con conjuntos** (no es Polars: una pasada por token, no por partida) | **Medido, junto con `_in_text`:** `resolve` 68,7 → ~49 s | 45 min | Bajo: las reglas de nivel son las mismas | `cmp` en sample y holdout (hecho) |
| **`_in_text` con `startswith`** si `whole_only` | Incluido arriba | 30 min | Bajo | `cmp` (hecho) |
| `read_csv` con solo las columnas usadas | Solo baja el pico de `load`, que no es el del run | 1 h | Bajo | `cmp` |
| Vectorizar las pasadas de `rules` | Máximo ~5 s de 8 | 4–6 h | Medio | `cmp` |
| Vectorizar el motor | Imposible sin rehacerlo: cada decisión depende del saldo de la anterior | | | |

### (b) Particionar por sociedad y cuenta

| Beneficio | Coste | Riesgo | Verificación |
| --- | --- | --- | --- |
| Estimado: como máximo 30 s y parte de los índices | 1–2 días | **Alto** | `cmp`, insuficiente: un caso que no esté en holdout puede cambiar en FINAL |

Los saldos son globales, `find` cruza sociedades a propósito (`parties.py:84`, la tesorería del grupo paga por sus filiales) y los pagos entre sociedades tocan partidas de otra. **No lo recomiendo.** Lo único seguro hoy es subir el pool de PDFs de 6 a 10 procesos:

| Cambio | Beneficio | Coste | Riesgo | Verificación |
| --- | --- | --- | --- | --- |
| **10 workers en `documents`** | **Medido:** PDFs 42,5 → 27–28 s; +0,5 GB antes del pico | 5 min | Bajo, pero contradice la nota de memoria de `backend/README.md` (máximo 6). Lo decide la orquestadora | `cmp` (hecho); `documents.parquet` igual (hecho) |

### (c) Rust con PyO3 y maturin

| Beneficio | Coste | Riesgo | Verificación |
| --- | --- | --- | --- |
| Estimado: como mucho 30 s de los 105 s, tras la fase 1 | 6–10 h | Alto hoy: añade una cadena de compilación el día de FINAL | `cmp`, más tests de equivalencia de `_cited` y `_in_text` |

Si algún día compensa, estas serían las funciones: `_cited` (`party_amount.py:271`), el filtro de `_match` (`:236`), `_in_text` (`parties.py:89`) y `_common_prefix` (`:118`).

Interfaz: por tercero, columnas Arrow de `compact`, `digits`, `po` y `replaced` con la fecha y la divisa, cargadas una vez desde Polars sin copia. Por llamada, los tokens y una fecha. Devuelve índices de `strong` y `weak` en el orden original. El saldo y `policy.py` se quedan en Python.

**No hoy.** La memoria no mejoraría sin mover también los índices, que es la parte cara. Después del evento, solo si TRAIN se vuelve necesario.

### (d) Carpeta de ejecución y precarga de `serve`

| Cambio | Beneficio | Coste | Riesgo | Verificación |
| --- | --- | --- | --- | --- |
| **`write_explanations` y `write_cases` fila a fila** | **Medido:** pico del run a ~5,6 GB; quita los ~21 GB de TRAIN | 20 min | Muy bajo | `explanations.jsonl.gz` idéntico con `cmp` (hecho); casos iguales salvo `createdAt` (hecho) |
| **`_RJEM_MALLOC_CONF`** antes de importar Polars | **Medido:** pico de 5,6 a 5,06 GB; sin pérdida de tiempo visible (105 s, 104 s sin él) | 15 min | Bajo: variable de entorno, no toca datos | `cmp` (hecho) |
| Caché de PDFs por hash del fichero | Estimado: `documents` 33 → ~12 s. 41.479 de 59.273 PDFs son de fases anteriores y se pueden dejar parseados | 2–3 h | Medio: una caché mal indexada cambia hechos. CONTRACT §3 ya contempla «misma caché» | `documents.parquet` igual; `cmp` |
| `explanations.parquet` junto al JSONL | Nada más allá de partir la sentencia (0,12 s frente a 0,74 s); cambia el contrato | 1 h | Bajo | |
| DuckDB en disco, caché entre arranques | Innecesario con 4,8 s | | | |
| Compartir cadenas en `reindex` | **Medido y descartado:** ~3 % en sample, sin efecto visible en el pico de holdout | | | |

### Recomendación

| Cuándo | Qué |
| --- | --- |
| **Hoy** | Partir la sentencia de `serve`, `write_*` fila a fila, `_RJEM_MALLOC_CONF`, `_cited`, `_in_text`. Con el visto bueno de la orquestadora, 10 workers |
| **Hoy, solo si sobra tiempo tras el ensayo de FINAL** | Caché de PDFs |
| **Después del evento** | Medir TRAIN con sondas, `maintain_order` en `load.py:187`, índices por tercero bajo demanda, y Rust solo si TRAIN lo pide |

## 7. Plan por fases

Cada fase termina con `just be-check`, `just be-test` y `cmp` contra la línea base. Una medición pesada a la vez, pedida a la orquestadora.

| Fase | Qué | Hito en holdout | Horas |
| --- | --- | --- | --- |
| **1. Memoria y `serve`** | Sentencia de `rows` en dos; `write_explanations` y `write_cases` fila a fila; `_RJEM_MALLOC_CONF` | `serve` ≤ 6 s y ≤ 2,5 GB; run ≤ 5,5 GB; CSV idéntico | 1 |
| **2. Motor** | `_cited`; `_in_text`; 10 workers si se aprueba | Run ≤ 110 s y ≤ 5,5 GB; CSV idéntico | 1 |
| **3. Opcional: caché de PDFs** | Por hash, solo de parsers | `documents` ≤ 15 s; `documents.parquet` igual; CSV idéntico | 2–3 |
| **4. Después del evento** | TRAIN con sondas; el resto de §6 | TRAIN completo < 25 min y < 16 GB (objetivo, sin medir) | |

Comprobación de cada fase:

```bash
cd backend && uv run closebooks run --phase holdout --out ../runs/perf-check
```

```bash
cmp runs/perf-holdout-a/submission.csv.gz runs/perf-check/submission.csv.gz
```

Lo mismo con `sample`, contra `runs/perf-sample-a`. **La línea base es de `64d6245`:** si entra un cambio de reglas, hay que regenerarla antes de comparar.

### Qué NO tocar

- Las reglas (`rules/*`, salvo reescribir `_cited` y `_in_text` con el mismo resultado), `policy.py`, `categories.py`, `state.py` en lo que decide, el orden de `resolve` ni `PASSES`.
- El orden de las listas del motor: `mine` se conserva tal cual. Por eso no se propone ordenar por fecha ni usar `bisect`.
- Las partidas cerradas: quitarlas del motor cambiaría `DUPLICATE_PAYMENT`.
- El evaluador oficial.
- `gzip` con `mtime=0` y nivel 6, para no cambiar los bytes.

## 8. Anexo: los cambios probados

Código de los prototipos, tal como se midieron.

**`CREATE TABLE rows`.** Materializar antes del join; el resto de la sentencia no cambia:

```sql
CREATE TEMP TABLE src AS SELECT row_number() OVER () AS rn, * FROM read_json(...);
CREATE TABLE rows AS SELECT ... FROM src r LEFT JOIN ... ASOF LEFT JOIN fx ...;
```

**`_cited`.** Mismos niveles; lo que dependía solo del token se calcula una vez por movimiento:

```python
def _cited(items, tokens):
    flats = [(token, _alnum(token)) for token in tokens]
    flats = [(t, f) for t, f in flats if len(f) >= MIN_SUFFIX]
    whole = {f for _, f in flats}
    names = {t for t, _ in flats}
    long_tails, short_tails = [], []
    for _, flat in flats:
        if flat.isdigit():
            core = flat.lstrip("0") or flat
            if len(core) >= STRONG_SUFFIX:
                long_tails.append(core)
            elif len(core) >= MIN_SUFFIX:
                short_tails.append(core)
    cuts = tuple(f for _, f in flats if len(f) >= MIN_CUT)
    long_tails, short_tails = tuple(long_tails), tuple(short_tails)
    strong, weak = [], []
    for item in items:
        po, compact, digits, replaced = item[5], item[6], item[7], item[8]
        if compact in whole or replaced in whole or (po and po in names) or digits.endswith(long_tails):
            strong.append(item)
        elif digits.endswith(short_tails) or compact.startswith(cuts):
            weak.append(item)
    return strong, weak
```

**`write_explanations`.** Igual `write_cases`:

```python
with (run / "explanations.jsonl.gz").open("wb") as raw, gzip.GzipFile(
        filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as gz:
    for r in rows:
        gz.write(orjson.dumps({...}, option=orjson.OPT_APPEND_NEWLINE))
```

**`_in_text`.** Con `whole_only`, en lugar de `_common_prefix`:

```python
if text.startswith(norm, position):
    best[party] = max(best.get(party, 0), len(norm))
```

Toda parte de `best` es entonces un nombre completo, así que `self.certain` queda en `True`.

**Asignador.** Antes de importar Polars; Polars pone sus valores delante y mandan los últimos:

```python
os.environ.setdefault("_RJEM_MALLOC_CONF", "dirty_decay_ms:0,muzzy_decay_ms:0")
```

## 9. Sin verificar

- Ningún prototipo se ha probado en LIVE, en `holdout-drift` ni con `--memory`; solo en sample y holdout.
- El `serve` corregido solo se midió hasta terminar la precarga, no con las pantallas abiertas.
- El tiempo de FINAL es una estimación por proporción. Lee dos fases previas, y eso no se ha medido.
- `_RJEM_MALLOC_CONF` se probó en el run, no en `serve`.
- Las causas marcadas como inferencia en §5.
