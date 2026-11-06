// The agent's decisions on a Dataset, produced by the backend. Mirrors CONTRACT.md; change both together.
import type { ObjectRef } from './dataset'

export type MatchStatus = 'matched' | 'suggested' | 'unmatched'
export type AlertType = 'duplicate' | 'tax_error' | 'bank_change' | 'unmatched' | 'po_mismatch' | 'other'
export type Severity = 'high' | 'medium' | 'low'

export interface RunMetrics {
  /** 0..1, only when there is a reference to compare with. */
  accuracy: number | null
  reconciliation: Record<MatchStatus, number>
  fraud: { detected: number; byType: Partial<Record<AlertType, number>> }
  autonomy: { auto: number; review: number }
  auditability: { withEvidence: number; total: number }
}

export interface Match {
  bankTransactionId: string
  status: MatchStatus
  targets: ObjectRef[]
  confidence: number | null
  rule: string
  differenceCents: number
}

export interface Alert {
  id: string
  type: AlertType
  severity: Severity
  entityId: string
  subject: ObjectRef
  amountCents: number
  currency: string
  title: string
  reason: string
  rule: string
  evidence: ObjectRef[]
  action: string
}

export interface Run {
  id: string
  createdAt: string
  period: string
  agent: { version: string; models: string[]; costUsd: number | null; durationMs: number | null }
  metrics: RunMetrics
  matches: Match[]
  alerts: Alert[]
}
