// The three kinds of work a person has in a run. Every open case is in exactly one queue: a question is a decision
// whatever its kind, and the rest go by kind.
import type { CaseRow } from './api'
import type { CaseKind } from './run'

export type QueueId = 'decidir' | 'revisar' | 'reclamar'

export const QUEUES: { id: QueueId; label: string; primary: string; description: string }[] = [
  { id: 'decidir', label: 'Decidir', primary: 'Responder la primera', description: 'Hay varias opciones con la misma evidencia: tu respuesta decide y puede quedar como regla.' },
  { id: 'revisar', label: 'Revisar', primary: 'Revisar el primero', description: 'Sin evidencia suficiente para casar: el sistema no fuerza nada y lo marca para que lo mires.' },
  { id: 'reclamar', label: 'Reclamar', primary: 'Escribir el primero', description: 'Movimientos ya conciliados que dejan algo que reclamar o aclarar con el tercero.' },
]

const KIND_QUEUE: Record<CaseKind, Exclude<QueueId, 'decidir'>> = {
  unidentified_receipt: 'revisar',
  ambiguous_match: 'revisar',
  unknown_debit: 'revisar',
  fx_difference: 'revisar',
  returned: 'revisar',
  new_bank_details: 'revisar',
  short_payment: 'reclamar',
  dispute: 'reclamar',
  overdue_customer: 'reclamar',
  overpayment: 'reclamar',
  duplicate_payment: 'reclamar',
  supplier_invoice_mismatch: 'reclamar',
  supplier_credit_pending: 'reclamar',
}

export const queueOfKind = (kind: string): Exclude<QueueId, 'decidir'> => KIND_QUEUE[kind as CaseKind] ?? 'revisar'

const kindsOf = (id: QueueId) => (Object.keys(KIND_QUEUE) as CaseKind[]).filter((k) => KIND_QUEUE[k] === id)

/** `status` and `kind` of the case list for a queue. */
export function queueFilter(id: QueueId): { status: string; kind?: string } {
  return id === 'decidir' ? { status: 'question' } : { status: 'needs_review,fallback', kind: kindsOf(id).join(',') }
}

/** The case the queue's primary action opens: in Reclamar, the first one that has an email to write. */
export function firstActionable<T extends Pick<CaseRow, 'suggestedAction'>>(id: QueueId, rows: readonly T[]): T | undefined {
  return id === 'reclamar' ? rows.find((r) => r.suggestedAction.startsWith('email_')) : rows[0]
}
