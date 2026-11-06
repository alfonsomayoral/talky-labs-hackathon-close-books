# CONTRACT.md

Lo que entrega el backend en cada ejecución y lo que la plataforma le devuelve. Es el **único punto de encuentro** entre `backend/` y `app/`: ninguno importa código del otro. El problema está en [PROBLEM.md](PROBLEM.md); el plan, en [docs/PLAN.md](docs/PLAN.md); cómo se produce, en [ARCHITECTURE.md](ARCHITECTURE.md) §7.

> **Estado:** v2 (7 nov 2026). Añade a la v1 los casos, los hechos, el estado, las preguntas, los borradores, la carpeta `human/` y la API. **Cualquier cambio a este fichero va en una PR propia, que fusiona la sesión orquestadora antes de que nadie lo use.**

## 1. Convenciones

- Una ejecución es una carpeta `runs/<fase>-<YYYYMMDD-HHMMSS>/` (ignorada por git). `<fase>` es `sample`, `train`, `holdout`, `holdout-drift`, `live`, `final` o el nombre de un zip subido.
- Dentro del backend, los importes van en **céntimos enteros** con su `currency`. En los ficheros de la ejecución y en la API, `amountCents` (entero) + `currency`, y `amountEur` (entero, céntimos de EUR al tipo del día) donde haga falta ordenar o sumar entre divisas. Solo `submission.csv.gz` escribe decimales.
- JSON con claves en `camelCase`. Fechas `YYYY-MM-DD`; instantes ISO 8601 con zona.
- Ids: `bankTxnId` (`BT-…`), `itemId` (`ARI-|ARC-|API-|APC-…`), `partyId` (`C…`/`S…` del maestro), `caseId` (`CASE-<bankTxnId>` o `CASE-<kind>-<n>`), `questionId`, `draftId`, `ruleId` (`MR-<n>`).
- `rule`: `<FAMILIA>-<CASO>` en mayúsculas (`FILE-DD-BATCH`, `ADVICE-CSV`, `REF-EXACT`, `PARTY-AMOUNT`, `HISTORY-DUPLICATE`, `CAT-CODE`, `MEMORY-RULE`, `ARBITER`, `FALLBACK-UNIDENTIFIED`, `FALLBACK-CATEGORY`).
- `SourceRef`: `{ "kind", "ref", "label"? }` con `kind` ∈ `remittanceAdvice`, `directDebitBatch`, `cardSettlement`, `chequeDeposit`, `paymentRun`, `pdf`, `customer`, `supplier`, `bankAccount`, `fxRate`, `bankLine`, `memoryRule`, `humanDecision`; `ref` es un id del dataset o una ruta relativa a la carpeta de la fase.

## 2. Ficheros de una ejecución

| Fichero | Qué es |
| --- | --- |
| `submission.csv.gz` | La entrega oficial (FORMAT.md). Lo único que se puntúa |
| `explanations.jsonl.gz` | Una línea por fila de `submission.csv.gz`, en el mismo orden |
| `cases.jsonl.gz` | Un caso por movimiento con algo que enseñar o decidir, y casos agregados (cliente vencido, proveedor con incidencia) |
| `facts/documents.parquet` | Hechos extraídos de avisos de remesa y PDFs |
| `facts/parties.parquet` | Tercero resuelto por movimiento |
| `state/open_items.parquet` | Saldo abierto por partida al final de la fase y su historia |
| `questions.jsonl` | Preguntas del agente a una persona |
| `drafts.jsonl` | Borradores de correo |
| `run.json` | Metadatos, recuentos, coste y puntuación |
| `human/decisions.jsonl` · `human/memory_rules.jsonl` · `human/outbox.jsonl` | Lo que escribe la plataforma (§4). El backend solo los lee |

### 2.1 `explanations.jsonl.gz`

```json
{"bankTxnId": "BT-2024-0079254", "itemId": "ARI-2023-2735920", "amountCents": 222734, "currency": "EUR",
 "category": null, "exception": null, "rule": "ADVICE-TXT", "confidence": 1.0, "partyId": "CES01001234",
 "reference": "AVISO 8826032134",
 "sources": [{"kind": "remittanceAdvice", "ref": "remittance_advices/ES01/RA_20240321_WELLNESSLOMA_862193.txt"}],
 "candidates": []}
```

| Campo | Tipo | Significado |
| --- | --- | --- |
| `bankTxnId`, `itemId`, `amountCents`, `currency`, `category`, `exception` | | Igual que la fila del CSV; `null` donde el CSV va vacío |
| `rule` | `string` | Regla que produjo la fila |
| `confidence` | `number` | 0..1 |
| `partyId` | `string \| null` | Tercero resuelto (cliente o proveedor por el que se paga, no el ordenante) |
| `reference` | `string \| null` | Lo que la regla extrajo del texto (número, referencia de aviso, mandato, id de remesa) |
| `sources` | `SourceRef[]` | Lo que respalda la fila, además del movimiento y la partida |
| `candidates` | `{itemId, amountCents, currency, why}[]` | Partidas consideradas y descartadas. Solo en reglas ambiguas y en `FALLBACK-*` (vacío si no hay) |

### 2.2 `cases.jsonl.gz`

Un caso es lo que la plataforma enseña y lo que una persona decide. Hay un caso por movimiento que **no** se cerró con `confidence` 1 por una regla de fichero o referencia, y casos agregados.

```json
{"caseId": "CASE-BT-2024-0028014", "kind": "unidentified_receipt", "status": "fallback", "priority": 2,
 "entity": "ES01", "bankTxnId": "BT-2024-0028014", "partyId": null, "itemIds": [],
 "amountCents": 12697, "currency": "EUR", "amountEur": 12697, "bookingDate": "2024-01-26",
 "summary": "Cobro de 126,97 EUR de MARIA VICENTE RUBIO sin tercero ni referencia. Hay 3 facturas abiertas con ese importe.",
 "suggestedAction": "ask", "questionId": "Q-000123", "draftId": null, "rule": "FALLBACK-UNIDENTIFIED",
 "createdAt": "2026-11-07T02:10:00+01:00"}
```

| Campo | Valores |
| --- | --- |
| `kind` | `unidentified_receipt`, `ambiguous_match`, `dispute` (`SHORT_DISPUTE` pendiente), `short_payment` (`PARTIAL` no explicado), `duplicate_payment`, `overpayment`, `returned` (`RETURNED`), `fx_difference`, `supplier_invoice_mismatch` (AP pagada por otro importe, dos veces, rechazada o cedida), `supplier_credit_pending` (`APC` sin compensar), `unknown_debit` (`FALLBACK-CATEGORY`), `overdue_customer` (agregado por cliente: saldo vencido), `new_bank_details` |
| `status` | `auto` (cerrado por el sistema, se enseña), `needs_review` (cerrado con confianza < 0,9), `question` (hay una `questionId`), `fallback` (sin casación), `done` (una persona lo marcó) |
| `priority` | 1 (alto) .. 3 |
| `suggestedAction` | `none`, `ask`, `email_customer`, `email_supplier`, `review` |

### 2.3 `facts/documents.parquet`

Una fila por **línea** de documento. Columnas: `docPath` (ruta relativa), `docKind` (`remittanceAdvice`, `invoicePdf`, `creditNotePdf`, `proformaPdf`, `bankAccountNotice`), `entity`, `payerName`, `receivedDate`, `paymentRef`, `paymentDate`, `paymentTotalCents`, `currency`, `lineNo`, `documentNumber` (tal cual), `documentNumberNorm`, `grossCents`, `deductionCents`, `reason`, `paidCents`, `customerPo`, `voucher`, `clause` (`instalments`, `retention`, `advance_deduction`, `replaces`, `service_month`, `rappel_offset`, `rappel_payout`, `credit_refund`, `factored`, `new_iban`; `null` en filas de aviso), `clauseValue` (JSON: `{"n":3,"amounts":[…]}`, `{"pct":10,"amountCents":…}`, `{"replaces":"FV22-0103565"}`…), `method` (`parser` | `model`), `model` (id o `null`), `cacheKey`.

### 2.4 `facts/parties.parquet`

Una fila por movimiento con tercero resuelto: `bankTxnId`, `partyId`, `partyKind` (`customer` | `supplier`), `payerName` (como viene del banco), `how` (`counterparty`, `iban`, `name`, `mandate`, `group`, `confirming`, `agency`, `factor`, `file`, `advice`, `memoryRule`), `confidence`, `alternatives` (JSON: `[{partyId, score}]`).

### 2.5 `state/open_items.parquet`

Una fila por partida con movimiento en la fase o abierta al inicio: `itemId`, `itemType`, `entity`, `partyId`, `documentNumber`, `issueDate`, `dueDate`, `currency`, `totalCents`, `openAtStartCents`, `appliedCents`, `openAtEndCents`, `status` (`open`, `partial`, `cleared`, `disputed`, `returned`), `history` (JSON: `[{bankTxnId, bookingDate, amountCents, exception}]`).

### 2.6 `questions.jsonl`

```json
{"questionId": "Q-000123", "caseId": "CASE-BT-2024-0028014", "bankTxnId": "BT-2024-0028014", "entity": "ES01",
 "question": "¿A qué factura corresponde este cobro de 126,97 EUR de MARIA VICENTE RUBIO?",
 "options": [{"id": "ARI-2023-1111111", "label": "FV23-0512345 · 126,97 EUR · Vicente Rubio Piscinas S.L. · vence 2024-01-15"},
             {"id": "ARI-2023-2222222", "label": "FV23-0517777 · 126,97 EUR · Jardines Vicente S.L. · vence 2024-02-01"},
             {"id": "none", "label": "Ninguna: dejar como no identificado"}],
 "defaultOption": "none",
 "rulePreview": {"kind": "payer_is_customer", "payerName": "MARIA VICENTE RUBIO", "partyId": "<la opción elegida>",
                  "description": "En adelante, los cobros de MARIA VICENTE RUBIO se asignan al cliente elegido"},
 "status": "open", "createdAt": "…"}
```

`status`: `open` | `answered`. La respuesta vive en `human/decisions.jsonl`.

### 2.7 `drafts.jsonl`

```json
{"draftId": "D-000045", "caseId": "CASE-…", "kind": "email_customer", "to": "cuentas.pagar@wellnessloma.example",
 "toName": "Wellness Lomaseca S.A.", "partyId": "CES01001234", "language": "es",
 "subject": "Facturas vencidas pendientes de pago", "body": "Estimados señores: …",
 "attachments": [{"kind": "pdf", "ref": "pdfs/ES01/ARI_FV240415058.pdf", "label": "FV24-0415058"}],
 "generatedBy": "claude-haiku-5-5", "status": "draft", "createdAt": "…"}
```

`kind`: `email_customer` (reclamación, duplicado a devolver, disputa, sobrepago) | `email_supplier` (importe que no cuadra, duplicado nuestro, abono pendiente). `status`: `draft` | `sent` | `manual` (la plataforma lo cambia en `human/outbox.jsonl`; el fichero del backend no se reescribe).

### 2.8 `run.json`

```json
{"runId": "live-20261107-021000", "phase": "live", "dataDir": "db/live", "createdAt": "…", "gitCommit": "5680257",
 "durationMs": 241000, "stages": {"load": 12000, "index": 8000, "documents": 90000, "rules": 70000, "resolve": 30000, "output": 31000},
 "txns": 203083, "rows": 748211, "byRule": {"FILE-DD-BATCH": 93786, "FALLBACK-UNIDENTIFIED": 4120},
 "byException": {"SHORT_DISCOUNT": 12000}, "byCategory": {"BANK_FEES": 9800},
 "cases": {"auto": 180000, "needs_review": 3000, "question": 400, "fallback": 2000},
 "models": {"claude-haiku-5-5": {"calls": 812, "inputTokens": 1200000, "outputTokens": 90000, "costUsd": 0.4}},
 "memoryRulesApplied": 12,
 "score": null}
```

`score` es la salida de `score_submission` del evaluador oficial (`score`, `metrics`, `segments`) cuando la fase tiene golden; si no, `null`. `stages` en milisegundos.

## 3. Invariantes

- Todos los `bank_txn_id` de la fase aparecen en `submission.csv.gz`, que pasa la validación de `bankrec_score.py` y pesa < 60 MB sin comprimir.
- Cada fila del CSV tiene exactamente una explicación con su `rule`. Sin evidencia, la fila sale de `FALLBACK-*`; nunca del candidato «más parecido».
- Ninguna partida se liquida por encima de su saldo abierto, salvo filas con `DUPLICATE_PAYMENT` u `OVERPAYMENT`.
- Misma fase, mismo commit, misma caché y misma carpeta `human/` dan el mismo CSV, byte a byte.
- El backend nunca escribe en `human/`; la plataforma nunca escribe fuera de `human/`.

## 4. Lo que escribe la plataforma: `human/`

| Fichero | Línea |
| --- | --- |
| `decisions.jsonl` | `{"decisionId", "questionId", "caseId", "optionId", "note", "saveAsRule": true, "by", "at"}` o `{"decisionId", "caseId", "action": "done" \| "review" \| "manual", "note", "by", "at"}` |
| `memory_rules.jsonl` | `{"ruleId": "MR-0001", "kind", "params", "description", "scope": {"entity"?}, "createdFrom": {"questionId"?, "caseId"?}, "by", "at", "active": true}`. `kind` ∈ `payer_is_customer` (`payerName` o `iban` → `partyId`), `reference_alias` (`pattern` → `documentNumber` o `partyId`), `supplier_nets_credit_notes` (`partyId`), `always_category` (`bank`, `bankCode`, `bankSubcode`, `textPattern` → `category`), `ignore_suffix` (`partyId`, `regex`), `parent_pays` (`payerPartyId` → `forPartyId`) |
| `outbox.jsonl` | `{"draftId", "status": "sent" \| "manual", "subject", "body", "to", "attachments", "by", "at"}`. «Enviado» es un registro: no sale ningún correo |

`closebooks run --memory runs/<id>/human/` carga las reglas activas y las aplica como `MEMORY-RULE` con `sources: [{"kind": "memoryRule", "ref": "MR-0001"}]`.

## 5. API (`closebooks serve`)

FastAPI en `http://localhost:8000`, solo lectura sobre `db/` y `runs/`, escritura solo en `runs/<id>/human/`. `openapi.json` versionado en `backend/openapi.json`; el frontend genera sus tipos de ahí. Listas paginadas: `{ "items": [...], "total": n, "page": p, "size": s }` (`size` ≤ 200). Errores `application/problem+json`. CORS abierto a `localhost`.

| Método y ruta | Devuelve |
| --- | --- |
| `GET /api/runs` | ejecuciones (resumen de `run.json`), más recientes primero |
| `GET /api/runs/{runId}` | `run.json` completo |
| `GET /api/runs/{runId}/stats?entity=` | KPIs: movimientos, % auto, importe identificado en EUR, por sociedad, por regla, por excepción, por categoría, por día, por estado de caso; `score` por segmento si hay golden |
| `GET /api/runs/{runId}/transactions?entity=&accountId=&rule=&exception=&category=&caseStatus=&q=&from=&to=&sort=&page=&size=` | movimientos con sus filas (asignaciones), `rule`, `partyId`, `caseId` |
| `GET /api/runs/{runId}/transactions/{bankTxnId}` | detalle: la línea del banco (todas las columnas), las filas con partida (número impreso, tercero, fechas, total, saldo), explicación, tercero, candidatos, evidencias con su contenido (`documents` con texto y hechos; ficheros de detalle con sus filas), otros movimientos relacionados (devolución ↔ original) |
| `GET /api/runs/{runId}/cases?status=&kind=&entity=&priority=&q=&sort=&page=&size=` · `GET /api/runs/{runId}/cases/{caseId}` | casos; el detalle incluye la pregunta y el borrador si los hay |
| `POST /api/runs/{runId}/cases/{caseId}/decision` `{action, note, by}` | escribe `human/decisions.jsonl`; devuelve el caso |
| `GET /api/runs/{runId}/questions?status=` · `POST /api/runs/{runId}/questions/{questionId}/answer` `{optionId, note, saveAsRule, by}` | pregunta; la respuesta escribe `decisions.jsonl` y, si `saveAsRule`, `memory_rules.jsonl` |
| `GET /api/runs/{runId}/drafts?status=` · `PUT /api/runs/{runId}/drafts/{draftId}` `{subject, body}` · `POST …/drafts/{draftId}/send` · `POST …/drafts/{draftId}/manual` | borradores; `send`/`manual` escriben `outbox.jsonl` |
| `POST /api/runs/{runId}/drafts` `{caseId, kind}` | genera un borrador bajo demanda (modelo) |
| `GET /api/runs/{runId}/memory-rules` · `POST` · `DELETE /{ruleId}` | reglas de memoria |
| `GET /api/runs/{runId}/open-items?entity=&partyId=&status=&overdue=true&page=&size=` | partidas con saldo e historia; `aging` agregado en `GET /api/runs/{runId}/aging?entity=` |
| `GET /api/runs/{runId}/parties/{partyId}` | tercero: maestro, grupo, partidas, movimientos, casos |
| `GET /api/data/{phase}/accounts` | cuentas (maestro + las vistas en los datos), formato por periodo, movimientos, saldo acumulado |
| `GET /api/data/{phase}/items?type=&entity=&partyId=&q=&page=&size=` · `GET /api/data/{phase}/parties?kind=&entity=&q=` · `GET /api/data/{phase}/documents?kind=&entity=&q=` · `GET /api/data/{phase}/documents/{path}` (texto y hechos) · `GET /api/data/{phase}/detail-files?kind=` | el paquete |
| `POST /api/uploads` (multipart zip) → `{uploadId, phase}` | descomprime en `db/<uploadId>/` (misma estructura que una fase) y detecta maestros |
| `POST /api/runs` `{phase, memoryFrom?}` → `{runId, status}` · `GET /api/runs/{runId}/status` | lanza `closebooks run` en segundo plano; estado y etapa actual |
| `POST /api/runs/{runId}/validate` | pasa `submission.csv.gz` por el validador oficial (sin golden): errores y tamaño |

**No hay endpoint de envío a la clasificación.** Lo hace una persona desde la terminal con el token en una variable de entorno.
