// Pure logic of the inbox: sort in the URL and age.
import type { SortState } from '@/components'

/** Most urgent first and, within a priority, the largest amount (CONTRACT.md §5.1). */
export const DEFAULT_SORT = 'priority,-amountEur'
const SORT_FIELDS = ['priority', 'amountEur', 'bookingDate']

export function sortFromParam(param: string | null): SortState | null {
  if (!param) return null
  const desc = param.startsWith('-')
  const columnId = desc ? param.slice(1) : param
  return SORT_FIELDS.includes(columnId) ? { columnId, direction: desc ? 'desc' : 'asc' } : null
}

export const sortToParam = (sort: SortState | null) => (sort ? `${sort.direction === 'desc' ? '-' : ''}${sort.columnId}` : null)

const DAY_MS = 86_400_000
const utc = (date: string) => Date.parse(`${date.slice(0, 10)}T00:00:00Z`)

/** Whole days from the booking date to the reference date (the end of the phase), never negative. */
export function ageDays(bookingDate: string | null, asOf: string): number | null {
  if (!bookingDate) return null
  return Math.max(0, Math.round((utc(asOf) - utc(bookingDate)) / DAY_MS))
}

export function ageLabel(days: number | null): string {
  if (days == null) return '—'
  return days < 60 ? `${days} d` : `${Math.round(days / 30)} meses`
}
