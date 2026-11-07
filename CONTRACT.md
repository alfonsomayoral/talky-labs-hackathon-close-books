# CONTRACT.md

Lo que entrega el backend en cada ejecución y lo que la plataforma le devuelve. Es el **único punto de encuentro** entre `backend/` y `app/`: ninguno importa código del otro. El problema está en [PROBLEM.md](PROBLEM.md); el plan, en [docs/PLAN.md](docs/PLAN.md); cómo se produce, en [ARCHITECTURE.md](ARCHITECTURE.md) §7.

> **Estado:** v2.2 (7 nov 2026): §5.2 fija las decisiones de `serve`. v2.1: §5.1 fija las formas de las respuestas. v2: Añade a la v1 los casos, los hechos, el estado, las preguntas, los borradores, la carpeta `human/` y la API. **Cualquier cambio a este fichero va en una PR propia, que fusiona la sesión orquestadora antes de que nadie lo use.**

## 1. Convenciones

- Una ejecución es una carpeta `runs/<fase>-<YYYYMMDD-HHMMSS>/` (ignorada por git). `<fase>` es `sample`, `train`, `holdout`, `holdout-drift`, `live`, `final` o el nombre de un zip subido.
- Dentro del backend, los importes van en **céntimos enteros** con su `currency`. En los ficheros de la ejecución y en la API, `amountCents` (entero) + `currency`, y `amountEur` (entero, céntimos de EUR al tipo del día) donde haga falta ordenar o sumar entre divisas. Solo `submission.csv.gz` escribe decimales.
- JSON con claves en `camelCase`. Fechas `YYYY-MM-DD`; instantes ISO 8601 con zona.
- Ids: `bankTxnId` (`BT-…`), `itemId` (`ARI-|ARC-|API-|APC-…`), `partyId` (`C…`/`S…` del maestro), `caseId` (`CASE-<bankTxnId>`; por partida, `CASE-<bankTxnId>-<itemId>`; agregados, `CASE-<kind>-<n>`), `questionId`, `draftId`, `ruleId` (`MR-<n>`).
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
| granularidad | Un caso por movimiento, salvo `supplier_invoice_mismatch`, `dispute` y `overdue_customer`: uno por (tercero, partida) con `partyId`, `itemIds` de esa partida y su importe. `status: auto` con `suggestedAction: email_*` = movimiento cerrado, incidencia viva. Un cargo categorizado sin casación no es `ambiguous_match`: va sin caso o como `unknown_debit` con `suggestedAction: none` |
| `priority` | 1 (alto) .. 3 |
| `suggestedAction` | `none`, `ask`, `email_customer`, `email_supplier`, `review` |
| `amountCents`, `amountEur` | **Magnitud positiva** siempre (también en cargos: el signo lo dice `kind` y el movimiento). En `stats`, `reviewQueueEur`, `byKind[].amountEur` e `identifiedEur` son sumas de magnitudes |

### 2.3 `facts/documents.parquet`

Una fila por **línea** de documento. Columnas: `docPath` (ruta relativa), `docKind` (`remittanceAdvice`, `invoicePdf`, `creditNotePdf`, `proformaPdf`, `bankAccountNotice`), `entity`, `payerName`, `receivedDate`, `paymentRef`, `paymentDate`, `paymentTotalCents`, `currency`, `lineNo`, `documentNumber` (tal cual), `documentNumberNorm`, `grossCents`, `deductionCents`, `reason`, `paidCents`, `customerPo`, `voucher`, `clause` (`instalments`, `retention`, `advance_deduction`, `replaces`, `service_month`, `rappel_offset`, `rappel_payout`, `credit_refund`, `factored`, `new_iban`; `null` en filas de aviso), `clauseValue` (JSON: `{"n":3,"amounts":[…]}`, `{"pct":10,"amountCents":…}`, `{"replaces":"FV22-0103565"}`…), `method` (`parser` | `model`), `model` (id o `null`), `cacheKey`.

### 2.4 `facts/parties.parquet`

Una fila por movimiento con tercero resuelto: `bankTxnId`, `partyId`, `partyKind` (`customer` | `supplier`), `payerName` (como viene del banco), `how` (`counterparty`, `iban`, `name`, `mandate`, `group`, `confirming`, `agency`, `factor`, `file`, `advice`, `memoryRule`), `confidence`, `alternatives` (JSON: `[{partyId, score}]`).

### 2.5 `state/open_items.parquet`

Una fila por partida **emitida en la fase**, abierta al inicio o con movimiento en la fase (también las que no tienen ningún movimiento: sin ellas el aging no es creíble): `itemId`, `itemType`, `entity`, `partyId`, `documentNumber`, `issueDate`, `dueDate`, `currency`, `totalCents`, `openAtStartCents`, `appliedCents`, `openAtEndCents`, `status` (`open`, `partial`, `cleared`, `disputed`, `returned`), `history` (JSON: `[{bankTxnId, bookingDate, amountCents, exception}]`).

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
 "txns": 203083, "rows": 748211, "csvBytes": 34120000, "byRule": {"FILE-DD-BATCH": 93786, "FALLBACK-UNIDENTIFIED": 4120},
 "byException": {"SHORT_DISCOUNT": 12000}, "byCategory": {"BANK_FEES": 9800},
 "cases": {"auto": 180000, "needs_review": 3000, "question": 400, "fallback": 2000},
 "models": {"claude-haiku-5-5": {"calls": 812, "inputTokens": 1200000, "outputTokens": 90000, "costUsd": 0.4}},
 "memoryRulesApplied": 12,
 "score": null}
```

`score` es la salida de `score_submission` del evaluador oficial (`score`, `metrics`, `segments`) cuando la fase tiene golden; si no, `null`. `stages` en milisegundos. `csvBytes` es el tamaño de `submission.csv.gz` **sin comprimir** (límite oficial: 60 MB).

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
| `memory_rules.jsonl` | `{"ruleId": "MR-0001", "kind", "params", "description", "scope": {"entity"?}, "createdFrom": {"questionId"?, "caseId"?}, "by", "at", "active": true}`. La API devuelve cada regla con `affectedTxns` (movimientos de la ejecución resueltos por `MEMORY-RULE` con ese `ruleId`; 0 si aún no se ha ejecutado con ella). `kind` ∈ `payer_is_customer` (`payerName` o `iban` → `partyId`), `reference_alias` (`pattern` → `documentNumber` o `partyId`), `supplier_nets_credit_notes` (`partyId`), `always_category` (`bank`, `bankCode`, `bankSubcode`, `textPattern` → `category`), `ignore_suffix` (`partyId`, `regex`), `parent_pays` (`payerPartyId` → `forPartyId`) |
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
| `GET /api/runs/{runId}/transactions/{bankTxnId}` | detalle (`party` es `null` cuando las filas del movimiento tienen más de un `partyId`; la evidencia de un fichero de detalle se filtra por el id de la remesa/liquidación/ingreso de la fila, no solo por número de documento): la línea del banco (todas las columnas), las filas con partida (número impreso, tercero, fechas, total, saldo), explicación, tercero, candidatos, evidencias con su contenido (`documents` con texto y hechos; ficheros de detalle con sus filas), otros movimientos relacionados (devolución ↔ original) |
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

### 5.1 Formas de las respuestas

Lo que §5 deja abierto. `camelCase`, `amountCents` + `currency`; `amountEur` y los campos `*Eur` en céntimos de EUR. Donde esta sección y `backend/openapi.json` difieran, manda `openapi.json` y se corrige esto. Los tipos de `Case`, `Question`, `Draft`, `Explanation`, `SourceRef`, `Candidate`, `Run` y `Score` son los de §2.

Añadidos a los parámetros de §5: `GET /api/data/{phase}/accounts?runId=` (rellena `reconciledRate`), `GET /api/runs/{runId}/aging?entity=&partyKind=customer|supplier`.

Definiciones: **cola de revisión** = casos `needs_review`, `question` o `fallback`. **Automático** = movimiento sin caso en la cola. **Identificado** = suma de `|amountEur|` de los movimientos con alguna fila con partida. Los importes de movimiento van con signo: + cobro, − pago.

| Ruta | Respuesta |
| --- | --- |
| `GET /api/runs` | `RunSummary[]` |
| `GET /api/runs/{runId}` | `Run` |
| `GET /api/runs/{runId}/stats` | `RunStats` |
| `GET /api/runs/{runId}/status` | `RunStatus` |
| `POST /api/runs/{runId}/validate` | `ValidationResult` |
| `POST /api/uploads` | `UploadResult` |
| `GET …/transactions` | `Paged<TxnRow>` |
| `GET …/transactions/{bankTxnId}` | `TxnDetail` |
| `GET …/cases` · `GET …/cases/{caseId}` · `POST …/decision` | `Paged<CaseRow>` · `CaseDetail` · `CaseDetail` |
| `GET …/questions` · `POST …/answer` | `Paged<Question>` · `CaseDetail` |
| `GET …/drafts` · `PUT` · `POST …/send` · `POST …/manual` · `POST …/drafts` | `Paged<Draft>` · `Draft` (con el estado de `outbox.jsonl` aplicado) |
| `GET …/memory-rules` · `POST` | `MemoryRule[]` · `MemoryRule`; a `POST` se le pasa `{kind, params, description, scope, createdFrom, by}` |
| `GET …/open-items` · `GET …/aging` | `Paged<OpenItem>` · `Aging` |
| `GET …/parties/{partyId}` | `PartyDetail` |
| `GET /api/data/{phase}/accounts` | `Account[]` |
| `GET /api/data/{phase}/items` · `parties` · `documents` · `documents/{path}` · `detail-files` | `Paged<DataItem>` · `Paged<Party>` · `Paged<DocumentRow>` · `DocumentDetail` · `Paged<DetailFileRow>` |

Los filtros de las listas (`entity`, `accountId`, `rule`, `exception`, `category`, `caseStatus`, `status`, `kind`, `priority`, `type`…) aceptan varios valores separados por coma. `sort` en las listas: `campo` o `-campo` (descendente), con `campo` una clave de la fila; admite varios criterios separados por coma (`sort=priority,-amountEur`). `GET …/transactions` admite además `statementFormat=` (n43, mt940, camt053; varios con coma). `q` busca sin distinguir mayúsculas ni acentos: en movimientos, en `bankTxnId`, `text`, `counterpartyName` y los números de partida; en casos, en `caseId`, `summary` y `partyName`.

```ts
export interface Paged<T> {
  items: T[]
  total: number
  page: number
  size: number
}

// ── Runs ─────────────────────────────────────────────────────────────────────

/** `GET /api/runs`: run.json without the breakdowns. */
export type RunSummary = Pick<Run, 'runId' | 'phase' | 'createdAt' | 'gitCommit' | 'durationMs' | 'txns' | 'rows' | 'cases' | 'memoryRulesApplied'> & {
  modelCalls: number
  modelCostUsd: number
  /** Total score (0..100) when the phase has a golden. */
  score: number | null
}

export interface EntityStats {
  entity: string
  name: string
  txns: number
  txnsAuto: number
  reviewQueue: number
  identifiedEur: number
}

export interface DayStats {
  date: string
  txns: number
  txnsAuto: number
  reviewQueue: number
  identifiedEur: number
}

export interface RunStats {
  runId: string
  phase: string
  /** The `?entity=` filter, or null for the whole group. */
  entity: string | null
  periodFrom: string
  periodTo: string
  txns: number
  /** Movements with no open case (no status needs_review, question or fallback). */
  txnsAuto: number
  /** Sum of |amountEur| of the movements with at least one row with an item. */
  identifiedEur: number
  /** Sum of |amountEur| of all the movements. */
  totalEur: number
  /** Cases with status needs_review, question or fallback. */
  reviewQueue: number
  reviewQueueEur: number
  byStatus: Partial<Record<CaseStatus, number>>
  byKind: { kind: string; cases: number; amountEur: number }[]
  byEntity: EntityStats[]
  byRule: { rule: string; rows: number; txns: number }[]
  byException: { exception: string; rows: number; amountEur: number }[]
  byCategory: { category: string; txns: number; amountEur: number }[]
  byDay: DayStats[]
  score: Score | null
}

export type RunState = 'queued' | 'running' | 'done' | 'failed'

export interface RunStatus {
  runId: string
  status: RunState
  /** Stage in progress (`load`, `index`, `documents`, `rules`, `resolve`, `output`), null when finished. */
  stage: string | null
  /** Milliseconds of the stages already finished. */
  stages: Record<string, number>
  startedAt: string
  finishedAt: string | null
  error: string | null
}

export interface ValidationResult {
  ok: boolean
  errors: { row: number | null; message: string }[]
  /** Bytes of submission.csv.gz. */
  sizeBytes: number
  /** Limit: 60 MB. */
  uncompressedBytes: number
  rows: number
  txns: number
}

export interface UploadResult {
  uploadId: string
  phase: string
}

// ── Transactions ─────────────────────────────────────────────────────────────

export interface Assignment {
  itemId: string | null
  documentNumber: string | null
  amountCents: number | null
  currency: string | null
  category: string | null
  exception: string | null
}

/** A row of `GET /transactions`. `amountCents` is signed: + receipt, − payment. */
export interface TxnRow {
  bankTxnId: string
  accountId: string
  entity: string
  bank: string
  statementFormat: string
  bookingDate: string
  amountCents: number
  currency: string
  amountEur: number
  text: string
  counterpartyName: string | null
  rule: string
  confidence: number
  partyId: string | null
  partyName: string | null
  caseId: string | null
  caseStatus: CaseStatus | null
  /** Rows of the movement in the submission. */
  rowCount: number
  /** The first 5 rows at most: the detail has them all. */
  assignments: Assignment[]
}

/** All the columns of bank_transactions.csv, as they come. */
export interface BankLine {
  bankTxnId: string
  accountId: string
  entity: string
  bank: string
  statementFormat: string
  statementFile: string
  bookingDate: string
  valueDate: string
  amountCents: number
  currency: string
  bankCode: string | null
  bankSubcode: string | null
  ref1: string | null
  ref2: string | null
  text: string
  counterpartyName: string | null
  counterpartyAccount: string | null
  endToEndId: string | null
  remittanceInfo: string | null
  origAmountCents: number | null
  origCurrency: string | null
}

export interface ItemSummary {
  itemId: string
  itemType: 'ARI' | 'ARC' | 'API' | 'APC'
  documentNumber: string
  partyId: string
  partyName: string
  issueDate: string
  dueDate: string | null
  currency: string
  totalCents: number
  openAtStartCents: number | null
  openAtEndCents: number | null
}

export interface DetailRow extends Explanation {
  item: ItemSummary | null
}

export interface PartyResolution {
  partyId: string
  partyName: string
  partyKind: 'customer' | 'supplier'
  payerName: string | null
  how: string
  confidence: number
  alternatives: { partyId: string; partyName: string; score: number }[]
}

/** One line of facts/documents.parquet (§2.3). */
export interface DocumentFact {
  lineNo: number | null
  documentNumber: string | null
  documentNumberNorm: string | null
  grossCents: number | null
  deductionCents: number | null
  reason: string | null
  paidCents: number | null
  currency: string | null
  customerPo: string | null
  voucher: string | null
  clause: string | null
  clauseValue: Record<string, unknown> | null
  method: 'parser' | 'model'
  model: string | null
}

export type EvidenceContent =
  | { type: 'document'; path: string; text: string | null; facts: DocumentFact[] }
  /** A detail file: only the rows of this movement, in the file's own columns. */
  | { type: 'detailFile'; path: string; columns: string[]; rows: string[][] }
  /** A master row, an FX rate, a memory rule…: label/value pairs. */
  | { type: 'record'; fields: Record<string, string | number | null> }
  | { type: 'none' }

export interface Evidence extends SourceRef {
  content: EvidenceContent
}

export interface RelatedTxn {
  bankTxnId: string
  bookingDate: string
  amountCents: number
  currency: string
  text: string
  /** `returnOf`, `returnedBy`, `duplicateOf`, `representmentOf`, `sameBatch`… */
  relation: string
}

export interface TxnDetail {
  txn: BankLine
  rows: DetailRow[]
  party: PartyResolution | null
  /** Union of the candidates of its rows. */
  candidates: Candidate[]
  /** Union of the sources of its rows, with their content. */
  evidence: Evidence[]
  related: RelatedTxn[]
  case: Case | null
}

// ── Cases ────────────────────────────────────────────────────────────────────

export interface CaseRow extends Case {
  partyName: string | null
}

export interface CaseDetail extends CaseRow {
  question: Question | null
  draft: Draft | null
}

// ── Open items and aging ─────────────────────────────────────────────────────

export interface ItemHistoryEntry {
  bankTxnId: string
  bookingDate: string
  amountCents: number
  exception: string | null
}

/** state/open_items.parquet (§2.5) */
export interface OpenItem {
  itemId: string
  itemType: 'ARI' | 'ARC' | 'API' | 'APC'
  entity: string
  partyId: string
  partyName: string
  documentNumber: string
  issueDate: string
  dueDate: string | null
  currency: string
  totalCents: number
  openAtStartCents: number
  appliedCents: number
  openAtEndCents: number
  openAtEndEur: number
  status: 'open' | 'partial' | 'cleared' | 'disputed' | 'returned'
  /** Days past due at the end of the phase; 0 if not due. */
  daysOverdue: number
  history: ItemHistoryEntry[]
}

export type AgingBucket = 'not_due' | 'd1_30' | 'd31_60' | 'd61_90' | 'd90_plus'

export interface AgingParty {
  partyId: string
  partyName: string
  entity: string
  openEur: number
  overdueEur: number
  buckets: Record<AgingBucket, number>
  openItems: number
  oldestDaysOverdue: number
  /** SHORT_DISPUTE still open. */
  disputes: number
  /** DUPLICATE_PAYMENT to give back. */
  duplicates: number
  caseId: string | null
}

/** `GET /aging?entity=&partyKind=customer|supplier`. All EUR cents. */
export interface Aging {
  asOf: string
  totals: Record<AgingBucket, number>
  openEur: number
  overdueEur: number
  /** Top 200 by overdueEur. */
  parties: AgingParty[]
}

// ── Package data ─────────────────────────────────────────────────────────────

export interface Party {
  partyId: string
  kind: 'customer' | 'supplier'
  entity: string
  name: string
  tradeName: string | null
  /** customer_type or supplier_type */
  type: string | null
  country: string | null
  taxId: string | null
  iban: string | null
  paymentTerms: string | null
  currency: string | null
  groupId: string | null
  parentId: string | null
  blockedSince: string | null
}

export interface PartyDetail {
  party: Party
  /** Other parties of the same group, including its parent. */
  group: Pick<Party, 'partyId' | 'name' | 'entity'>[]
  /** First 200 by due date. */
  items: OpenItem[]
  /** Last 200. */
  transactions: TxnRow[]
  cases: CaseRow[]
}

export interface Account {
  accountId: string
  entity: string
  bank: string
  bankName: string | null
  currency: string
  iban: string | null
  purpose: string | null
  /** False when it appears in the data but not in the master. */
  inMaster: boolean
  /** Statement format by period: `to` is null for the current one. */
  formats: { format: string; from: string; to: string | null }[]
  txns: number
  inflowCents: number
  outflowCents: number
  /** inflow − outflow in the phase, in the account's currency. */
  netCents: number
  firstDate: string | null
  lastDate: string | null
  /** Only with `?runId=`: share of movements with no open case. */
  reconciledRate: number | null
}

export interface DataItem {
  itemId: string
  itemType: 'ARI' | 'ARC' | 'API' | 'APC'
  entity: string
  documentNumber: string
  partyId: string
  partyName: string
  issueDate: string
  dueDate: string | null
  currency: string
  totalCents: number
  /** Only in the items open at the start of the phase. */
  openAtStartCents: number | null
  relatedDocument: string | null
  reference: string | null
}

export interface DocumentRow {
  path: string
  kind: 'remittanceAdvice' | 'invoicePdf' | 'creditNotePdf' | 'proformaPdf' | 'bankAccountNotice'
  entity: string
  format: string
  name: string
  date: string | null
  /** Payer of an advice, or party of a PDF. */
  partyName: string | null
}

export interface DocumentDetail extends DocumentRow {
  text: string | null
  facts: DocumentFact[]
}

export interface DetailFileRow {
  path: string
  kind: 'directDebitBatch' | 'cardSettlement' | 'chequeDeposit' | 'paymentRun'
  entity: string
  month: string | null
  rows: number
}
```

### 5.2 Decisiones de la implementación de `serve` (v2.2)

Fijadas al integrar la API; mandan sobre lo que §4 y §5 dejaban abierto.

1. `PUT …/drafts/{id}` guarda la edición en `human/outbox.jsonl` con `status: "draft"` y `by: null`; gana el último registro por `draftId`. `send` y `manual` añaden su registro después.
2. `DELETE …/memory-rules/{ruleId}` añade a `memory_rules.jsonl` la regla con `active: false` y `deletedAt`; gana el último registro por `ruleId`; responde 204. `closebooks run --memory` aplica la misma regla de «último registro».
3. `stats.byKind` cuenta solo los casos de la cola de revisión (`needs_review`, `question`, `fallback`).
4. Tras una decisión: `done` y `manual` dejan el caso en `done`; `review` en `needs_review`; responder una pregunta cierra su caso. Volver a responder una pregunta devuelve 409.
5. `saveAsRule` crea la regla a partir de `rulePreview`; si la opción elegida es una partida, el `partyId` es el de su tercero; la opción `none` no crea regla.
6. `aging` usa `partyKind=customer` por defecto y solo cuenta facturas con saldo final > 0 (no abonos).
7. `RunStatus.stage` es aproximado (`load` u `output`) mientras `closebooks run` solo escriba `run.json` al final.
8. `POST /api/runs` con `memoryFrom` copia `memory_rules.jsonl` a la nueva ejecución; la aplicación de reglas llega con `--memory`.
9. Relaciones entre movimientos en el detalle: `returnOf`, `returnedBy`, `duplicateOf`, `duplicatedBy`, `sameItem`.
10. En `documents`, la fecha y el `partyName` de un PDF se deducen del nombre del fichero y de su partida; en avisos, `partyName` es `null`.
11. `POST …/drafts` responde 501 hasta que exista el generador de borradores.
12. `closebooks serve <run>` marca esa ejecución con `served: true` en `RunSummary` (las demás `false`) y es la única que precarga; la plataforma la elige por defecto. Las demás se abren bajo demanda (primera apertura, segundos).
13. `GET …/cases` devuelve además `sumAmountEur`: suma de `amountEur` de todos los casos que cumplen el filtro, no solo de la página.
15. `serve` no acepta conexiones hasta terminar la precarga de la ejecución servida (la primera petición nunca paga los ~30 s de apertura).
16. `summary` de un caso describe lo resuelto (regla, partidas, excepción), nunca «sin casación» si hay filas con partida. `TxnDetail.party` solo es `null` con más de un `partyId` distinto; con 27 filas del mismo cliente lleva ese tercero con su `how` y confianza.
14. El esquema OpenAPI de `ValidationResult.errors` es `{row: number | null, message: string}` (nombre de esquema propio, sin chocar con el `ValidationError` de FastAPI).
