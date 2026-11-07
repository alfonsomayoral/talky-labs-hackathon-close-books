# scripts/analysis

Scripts que producen las cifras de `docs/ANALYSIS.md`. Leen el paquete oficial de `db/` (nunca lo modifican) y
escriben Parquet y JSON en `runs/analysis/` (ignorado por git). Imprimen tablas en Markdown.

Requisitos: Python ≥ 3.12 y [uv](https://docs.astral.sh/uv/). Cada script lleva sus dependencias en la cabecera
(PEP 723), así que basta con:

```bash
uv run scripts/analysis/01_volumes.py
```

| Script | Qué mide |
| --- | --- |
| `01_volumes.py` | Volúmenes por fase, sociedad, cuenta, formato de extracto y divisa; partidas y documentos |
| `02_golden.py` | Golden de TRAIN por segmento y dificultad, en movimientos y pares; excepciones y categorías |
| `03_sources.py` | Qué fuente resuelve cada segmento: texto del banco, importe, ficheros de detalle, avisos de remesa, PDFs |
| `04_drift.py` | Drift TRAIN → LIVE: Norma 43 → camt.053, avisos de remesa, ZA01/ZAR, IT01, clientes nuevos |
| `05_baseline.py` | Puntúa el starter oficial sobre TRAIN con `bankrec_score.py` y calcula el techo de puntos por segmento |
| `07_final_rehearsal.py` | Ensayo de FINAL: copia una fase con una sociedad, un banco, un formato y una divisa no vistos, y compara el run con el de la fase original. Corre con el entorno de `backend/` (ver su cabecera) |

El starter y el evaluador oficiales viven en `db/bankrec-docs-and-masters/starter/`; `05_baseline.py` los importa de ahí.
