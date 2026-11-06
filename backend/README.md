# backend/

El conciliador bancario. Lee una fase de `db/` y escribe en `runs/` la carpeta de [`../CONTRACT.md`](../CONTRACT.md). Las reglas deciden; los modelos solo extraen ([`../ARCHITECTURE.md`](../ARCHITECTURE.md) §7).

```bash
just be-run sample        # ejecuta una fase: sample, train, live, holdout, holdout-drift, final
just be-score <run>       # puntúa con el evaluador oficial, por segmento; --compare <run> enseña qué baja
just holdout              # construye db/holdout/ y db/holdout-drift/ desde TRAIN
just be-check && just be-test
```
