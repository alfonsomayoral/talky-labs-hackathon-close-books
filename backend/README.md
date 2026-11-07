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

`_RJEM_MALLOC_CONF=dirty_decay_ms:0,muzzy_decay_ms:0` hace que Polars devuelva al sistema la memoria que libera: tras `load` en holdout, 950 MB de RSS frente a 1,8 GB. Lo fijan `closebooks/__init__.py`, si la variable no está ya definida, y el `justfile`. FINAL corre con ella.

## Parámetros del motor que no salen de los datos

Son cotas de búsqueda, no valores aprendidos. Un candidato solo se acepta si es la única solución.

| Constante | Valor | Qué acota |
| --- | --- | --- |
| `MAX_FULL_SEARCH` | 22 | Facturas abiertas del tercero en la búsqueda completa de un subconjunto: cota de tiempo por movimiento |
| `MAX_SKIPPED` | 2 | Facturas que un cliente puede saltarse dentro de la ventana que paga |
| `MAX_CHANCE` | 0,05 | Conjuntos que se esperaría que sumaran el cobro por azar (conjuntos buscados ÷ céntimos que suman las candidatas). Por encima, una solución única no prueba nada y no se toma. Se fijó de antemano, no mirando el golden |
