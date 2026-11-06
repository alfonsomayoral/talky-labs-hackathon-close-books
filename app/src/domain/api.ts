// Response shapes of the API (CONTRACT.md §5.1), by hand until backend/openapi.json exists; then it wins:
// `npm run gen:api` writes api.generated.ts, and each type here becomes an alias of its schema
// (`export type RunStats = components['schemas']['RunStats']`), so no view has to change.
import type { Case, CaseStatus, Candidate, Draft, Explanation, Question, Run, Score, SourceRef } from './run'

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
