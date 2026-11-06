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
