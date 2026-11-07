# backend/

El conciliador bancario. Lee una fase de `db/` y escribe en `runs/` la carpeta de [`../CONTRACT.md`](../CONTRACT.md). Las reglas deciden; los modelos solo extraen ([`../ARCHITECTURE.md`](../ARCHITECTURE.md) §7).

```bash
just be-run sample        # ejecuta una fase: sample, train, live, holdout, holdout-drift, final
just be-score <run>       # puntúa con el evaluador oficial, por segmento; --compare <run> enseña qué baja
just holdout              # construye db/holdout/ y db/holdout-drift/ desde TRAIN
just be-check && just be-test
```

## API

`just be-serve [run]` serves CONTRACT §5 on `localhost:8000`. After changing a route or a schema, regenerate the
versioned spec (a test fails if it is stale):

```
cd backend && uv run python -c "import json; from pathlib import Path; from closebooks.api.app import create_app; from closebooks.api.store import Store; Path('openapi.json').write_text(json.dumps(create_app(store=Store(Path('/none'))).openapi(), indent=2, ensure_ascii=False) + chr(10))"
```

## Tabla de categorías

`src/closebooks/data/category_codes.csv` (banco, código, subcódigo y dirección, solo conteos) se aprende de TRAIN con `tools/learn_categories.py`; ejecútalo con `uv run python -m closebooks.tools.learn_categories`. La versionada usa todo TRAIN, así que el holdout con esa tabla está contaminado: para una medida limpia, apréndela con un corte anterior a 2025 y apunta la ejecución con `CLOSEBOOKS_CATEGORY_CODES=<ruta>`. En FINAL, un banco o código nuevo no está en la tabla: cae en `CAT-TEXT` y, si no, en el respaldo.

## Memoria

Dos pánicos de kernel la noche del 6 al 7 de noviembre coincidieron con memoria agotada por procesos Python (un proceso de 97 GB, compresor saturado). Una ejecución de `holdout` debe quedar por debajo de 8 GB de RSS: mídelo con `/usr/bin/time -l uv run closebooks run --phase holdout --out ../runs/holdout-mem`. FINAL corre con la plataforma y `serve` arriba, así que ese es el límite que importa. Una medición pesada a la vez; los pools no pasan de 6 procesos.

Las salidas CSV/JSONL se escriben por bloques, y el motor comparte un único índice de partidas con saldos y totales
en vectores de enteros de 64 bits. El historial conserva los mismos campos al exportarse.

La resolución escribe asignaciones y explicaciones por movimiento, sin acumular todas las filas ni un diccionario
con todos los movimientos. Las facturas permanecen en tablas por columnas; solo se materializan las referencias
encontradas y las candidatas emitidas, abiertas y no reservadas. Las referencias, prefijos, sufijos y pedidos usan hashes
compactos, comprobando los campos originales antes de aceptar un candidato. Un cobro explicado por sus referencias
no necesita materializar todo el historial del tercero.

El historial de liquidaciones usa vectores de eventos enlazados por posición de partida. Su exportación a Parquet
se ejecuta por lotes. `progress.json` y stderr conservan etapas, movimientos completados y pico RSS durante el run;
el estado de la API consulta ese progreso porque el CSV se abre desde el inicio de la resolución.

En las fases con golden, `run` termina un proceso de conciliación antes de cargar el evaluador en el proceso
coordinador: sus estados grandes no conviven. `peakRssMb.score` mide ese segundo proceso; los otros valores son
máximos acumulados del proceso de conciliación, sin sumar los workers de documentos.

Para generar los artefactos sin cargar el golden y puntuar después:

```bash
uv run closebooks run --phase train --out ../runs/train-mem --no-score
uv run closebooks score ../runs/train-mem
```

`--no-score` deja `score: null` en `run.json`. El comando `score` imprime el resultado; no modifica los metadatos.
