# CONTRACT.md

Lo que entrega el backend en cada ejecución: la **entrega oficial** que se puntúa y la **explicación** de cada fila. El problema está en [PROBLEM.md](PROBLEM.md); cómo se produce, en [ARCHITECTURE.md](ARCHITECTURE.md) §7.

> **Estado:** v1 (6 nov 2026). Sustituye al `Run` v0 de matches y alertas, que modelaba un cierre contable que no es el reto. Ese tipo sigue en [`app/src/domain/run.ts`](app/src/domain/run.ts) porque el frontend está congelado en la fase 0 (ARCHITECTURE.md §3), pero ya no lo produce nadie.

## Convenciones

- Una ejecución es una carpeta `runs/<fase>-<YYYYMMDD-HHMMSS>/`, ignorada por git. `<fase>` es `sample`, `train`, `live` o `final`.
- Dentro del backend, los importes van en **céntimos enteros** con su `currency`. Solo `submission.csv.gz` los escribe con dos decimales, porque lo exige el formato oficial.
- JSON con claves en `camelCase`. Fechas ISO 8601.

## Ficheros

| Fichero | Qué es |
| --- | --- |
| `submission.csv.gz` | La entrega, en el formato oficial (PROBLEM.md §6). Es lo único que se puntúa |
| `explanations.jsonl.gz` | Una línea por fila de `submission.csv.gz`, en el mismo orden |
| `run.json` | Metadatos de la ejecución y, si la fase tiene golden, su puntuación |

### `explanations.jsonl.gz`

```json
{"bankTxnId": "BT-2024-0079254", "itemId": "ARI-2023-2735920", "amountCents": 222734, "currency": "EUR",
 "category": null, "exception": null, "rule": "RA-ADVICE-LIST", "confidence": 1.0,
 "sources": [{"kind": "remittanceAdvice", "ref": "remittance_advices/ES01/RA_20240321_WELLNESSLOMA_862193.txt"}]}
```

| Campo | Tipo | Significado |
| --- | --- | --- |
| `bankTxnId` | `string` | Movimiento, igual que en el CSV |
| `itemId` | `string \| null` | Partida; `null` en la fila sin partida |
| `amountCents` · `currency` | `number \| null` · `string \| null` | Importe de la fila en la divisa de la partida; `null` en la fila sin partida |
| `category` · `exception` | `string \| null` | Igual que en el CSV; `null` si está vacío |
| `rule` | `string` | Regla que produjo la fila: `<FAMILIA>-<CASO>` en mayúsculas, p. ej. `AGG-DD-BATCH`, `REF-EXACT`, `FALLBACK-UNIDENTIFIED` |
| `confidence` | `number \| null` | 0..1, si la regla la calcula |
| `sources` | `SourceRef[]` | Lo que respalda la fila, además del propio movimiento y la partida |

`SourceRef` es `{ "kind": string, "ref": string }`. `kind` es uno de `remittanceAdvice`, `directDebitBatch`, `cardSettlement`, `chequeDeposit`, `paymentRun`, `pdf`, `customer`, `supplier`, `fxRate` o `bankLine` (otro movimiento, como el cobro original de una devolución). `ref` es un id del dataset o una ruta relativa a la carpeta de la fase.

### `run.json`

```json
{
  "phase": "train",
  "createdAt": "2026-11-07T12:30:00+01:00",
  "gitCommit": "5680257",
  "durationMs": 241000,
  "rows": 5403411,
  "byRule": { "AGG-DD-BATCH": 713554, "FALLBACK-UNIDENTIFIED": 41200 },
  "models": ["claude-haiku-5-5"],
  "costUsd": 3.1,
  "score": null
}
```

`score` es la salida de `score_submission` del evaluador oficial (`score`, `metrics` y `segments`). Si la fase no tiene golden, `null`.

## Invariantes

- Todos los `bank_txn_id` de la fase aparecen en `submission.csv.gz`.
- `submission.csv.gz` pasa la validación de `bankrec_score.py`.
- Cada fila del CSV tiene exactamente una explicación con su `rule`. Las filas sin evidencia que las respalde salen de una regla `FALLBACK-*`, nunca de una casación forzada.
- Misma fase, mismo commit y misma caché de extracción dan el mismo CSV, byte a byte.
