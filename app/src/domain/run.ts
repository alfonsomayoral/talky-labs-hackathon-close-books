// What one execution writes (CONTRACT.md §1, §2 and §4). Pure types: no React, no I/O.
// Amounts are integer cents with their currency; `amountEur` is integer EUR cents at the day's rate.

export type SourceKind =
  | 'remittanceAdvice'
  | 'directDebitBatch'
  | 'cardSettlement'
  | 'chequeDeposit'
  | 'paymentRun'
  | 'pdf'
  | 'customer'
  | 'supplier'
  | 'bankAccount'
  | 'fxRate'
  | 'bankLine'
  | 'memoryRule'
  | 'humanDecision'

export interface SourceRef {
  kind: SourceKind
  ref: string
  label?: string
}

export interface Candidate {
  itemId: string
  amountCents: number
  currency: string
  why: string
}

/** One line per row of submission.csv.gz (§2.1). */
export interface Explanation {
  bankTxnId: string
  itemId: string | null
  amountCents: number | null
  currency: string | null
  category: string | null
  exception: string | null
  rule: string
  confidence: number
  partyId: string | null
  reference: string | null
  sources: SourceRef[]
  candidates: Candidate[]
}

export type CaseKind =
  | 'unidentified_receipt'
  | 'ambiguous_match'
  | 'dispute'
  | 'short_payment'
  | 'duplicate_payment'
  | 'overpayment'
  | 'returned'
  | 'fx_difference'
  | 'supplier_invoice_mismatch'
  | 'supplier_credit_pending'
  | 'unknown_debit'
  | 'overdue_customer'
  | 'new_bank_details'

export type CaseStatus = 'auto' | 'needs_review' | 'question' | 'fallback' | 'done'
export type CasePriority = 1 | 2 | 3
export type SuggestedAction = 'none' | 'ask' | 'email_customer' | 'email_supplier' | 'review'

/** §2.2. `bankTxnId` is null in aggregate cases (overdue customer, supplier with an incident). */
export interface Case {
  caseId: string
  kind: CaseKind
  status: CaseStatus
  priority: CasePriority
  entity: string
  bankTxnId: string | null
  partyId: string | null
  itemIds: string[]
  amountCents: number
  currency: string
  amountEur: number
  bookingDate: string | null
  summary: string
  suggestedAction: SuggestedAction
  questionId: string | null
  draftId: string | null
  rule: string | null
  createdAt: string
}

export interface QuestionOption {
  id: string
  label: string
}

export interface RulePreview {
  kind: MemoryRuleKind
  description: string
  [param: string]: unknown
}

/** §2.6 */
export interface Question {
  questionId: string
  caseId: string
  bankTxnId: string | null
  entity: string
  question: string
  options: QuestionOption[]
  defaultOption: string
  rulePreview: RulePreview | null
  status: 'open' | 'answered'
  createdAt: string
}

export interface DraftAttachment {
  kind: string
  ref: string
  label?: string
}

export type DraftKind = 'email_customer' | 'email_supplier'
export type DraftStatus = 'draft' | 'sent' | 'manual'

/** §2.7 */
export interface Draft {
  draftId: string
  caseId: string
  kind: DraftKind
  to: string
  toName: string
  partyId: string | null
  language: string
  subject: string
  body: string
  attachments: DraftAttachment[]
  generatedBy: string | null
  status: DraftStatus
  createdAt: string
}

export interface ModelUsage {
  calls: number
  inputTokens: number
  outputTokens: number
  costUsd: number
}

/** The official scorer's output (`score_submission`): keys as it writes them. */
export interface Score {
  score: number
  metrics: Record<string, number>
  segments: Record<string, Record<string, number>>
}

/** run.json (§2.8) */
export interface Run {
  runId: string
  phase: string
  dataDir: string
  createdAt: string
  gitCommit: string
  durationMs: number
  stages: Record<string, number>
  txns: number
  rows: number
  /** Uncompressed bytes of submission.csv.gz (the limit is 60 MB). */
  csvBytes?: number
  byRule: Record<string, number>
  byException: Record<string, number>
  byCategory: Record<string, number>
  cases: Partial<Record<CaseStatus, number>>
  models: Record<string, ModelUsage>
  memoryRulesApplied: number
  score: Score | null
}

// human/: what the platform writes (§4).

export type MemoryRuleKind =
  | 'payer_is_customer'
  | 'reference_alias'
  | 'supplier_nets_credit_notes'
  | 'always_category'
  | 'ignore_suffix'
  | 'parent_pays'

export interface MemoryRule {
  ruleId: string
  kind: MemoryRuleKind
  params: Record<string, unknown>
  description: string
  scope: { entity?: string }
  createdFrom: { questionId?: string; caseId?: string }
  by: string
  at: string
  active: boolean
}

export type CaseDecisionAction = 'done' | 'review' | 'manual'
