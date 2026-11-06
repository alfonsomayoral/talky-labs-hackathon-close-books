// Pure logic of Proveedores: which cases belong, sort in the URL, age, email state, partial sums and the open items to show.
import { AGING_BUCKETS, AGING_LABEL, INBOX_STATUSES, type AgingBucket, type CaseRow, type CaseStatus, type OpenItem } from '@/domain'
import type { ProgressSegment, SortState } from '@/components'

/** Supplier cases the API can filter by kind. Duplicate payments to suppliers are left out: the API cannot filter by party kind. */
export const SUPPLIER_KINDS = ['supplier_invoice_mismatch', 'supplier_credit_pending']

/** Open states plus handled, so a person can look back at what was already sent. */
export const SUPPLIER_STATUSES: CaseStatus[] = [...INBOX_STATUSES, 'done']

/** The default list is what is still open; choosing «Gestionado» opens the rest. */
export function listStatuses(chosen: string[]): string {
  const valid = SUPPLIER_STATUSES.filter((s) => chosen.includes(s))
  return (valid.length ? valid : INBOX_STATUSES).join(',')
}

/** Kinds to ask for: the chosen ones that are supplier kinds, or both. */
export function listKinds(chosen: string[]): string {
  const valid = SUPPLIER_KINDS.filter((k) => chosen.includes(k))
  return (valid.length ? valid : SUPPLIER_KINDS).join(',')
}

/** Most urgent first, then the biggest amount. */
export const DEFAULT_SORT = 'priority,-amountEur'
const SORT_FIELDS = ['partyName', 'kind', 'amountEur', 'bookingDate']

export function sortFromParam(param: string | null): SortState | null {
  if (!param) return null
  const desc = param.startsWith('-')
  const columnId = desc ? param.slice(1) : param
  return SORT_FIELDS.includes(columnId) ? { columnId, direction: desc ? 'desc' : 'asc' } : null
}

export const sortToParam = (sort: SortState | null) => (sort ? `${sort.direction === 'desc' ? '-' : ''}${sort.columnId}` : null)

const DAY_MS = 86_400_000
const utc = (date: string) => Date.parse(`${date.slice(0, 10)}T00:00:00Z`)

/** Whole days from the booking date to the end of the phase, never negative. */
export function ageDays(bookingDate: string | null, asOf: string): number | null {
  if (!bookingDate) return null
  return Math.max(0, Math.round((utc(asOf) - utc(bookingDate)) / DAY_MS))
}

export function ageLabel(days: number | null): string {
  if (days == null) return '—'
  if (days === 0) return 'hoy'
  return days < 60 ? `${days} d` : `${Math.round(days / 30)} meses`
}

export type EmailState = 'none' | 'draft' | 'closed'

/** The case row only says whether a draft exists; whether it went out is in the panel. */
export function emailState(c: Pick<CaseRow, 'status' | 'draftId' | 'suggestedAction'>): EmailState {
  if (c.status === 'done') return 'closed'
  if (c.suggestedAction !== 'email_supplier') return 'none'
  return c.draftId ? 'draft' : 'none'
}

/** Sum of the EUR amounts loaded; `complete` is false while more rows remain on the server. */
export function loadedSum(rows: Pick<CaseRow, 'amountEur'>[], total: number | null): { cents: number; complete: boolean } {
  return { cents: rows.reduce((acc, r) => acc + r.amountEur, 0), complete: total != null && rows.length >= total }
}

/** Items of the supplier with those of the case first, each group in the order received. */
export function orderItems(items: OpenItem[], caseItemIds: string[]): { item: OpenItem; inCase: boolean }[] {
  const mine = new Set(caseItemIds)
  const tagged = items.map((item) => ({ item, inCase: mine.has(item.itemId) }))
  return [...tagged.filter((t) => t.inCase), ...tagged.filter((t) => !t.inCase)]
}

const BUCKET_TONE: Record<AgingBucket, ProgressSegment['tone']> = { not_due: 'neutral', d1_30: 'info', d31_60: 'warn', d61_90: 'warn', d90_plus: 'danger' }

/** One segment per aging bucket in display order, in EUR cents. */
export const agingSegments = (totals: Record<AgingBucket, number>): ProgressSegment[] =>
  AGING_BUCKETS.map((b) => ({ value: Math.max(0, totals[b] ?? 0), tone: BUCKET_TONE[b], label: AGING_LABEL[b] }))
