// Pure logic of the reconciliation screen: URL filters → API params, facet options, table cells.
import type { Account, CaseStatus, RunStats, TxnRow } from '@/domain'
import { CASE_STATUS_LABEL, exceptionLabel, INBOX_STATUSES } from '@/domain'
import type { SortState } from '@/components'

export type FacetKey = 'entity' | 'account' | 'rule' | 'exception' | 'category' | 'status'

/** URL param and API param of each facet. `entity` is a facet only when the shell has no scope. */
export const FACETS: Record<FacetKey, { param: string; api: string }> = {
  entity: { param: 'sociedades', api: 'entity' },
  account: { param: 'cuenta', api: 'accountId' },
  rule: { param: 'regla', api: 'rule' },
  exception: { param: 'excepcion', api: 'exception' },
  category: { param: 'categoria', api: 'category' },
  status: { param: 'estado', api: 'caseStatus' },
}

export type Facets = Record<FacetKey, string[]>

export interface TxnFilters {
  q: string
  /** Entity scope of the shell (`?sociedad=`). */
  entity: string | null
  facets: Facets
  sort: SortState | null
}

export function toApiParams({ q, entity, facets, sort }: TxnFilters): Record<string, string | undefined> {
  const params: Record<string, string | undefined> = { q: q.trim() || undefined, sort: sortToParam(sort) ?? undefined }
  for (const key of Object.keys(FACETS) as FacetKey[]) {
    if (facets[key].length) params[FACETS[key].api] = facets[key].join(',')
  }
  if (entity) params.entity = entity
  return params
}

/** Column ids are the API's sort keys, so the sort goes to the URL and the API as it is. */
export const sortToParam = (sort: SortState | null) => (sort ? `${sort.direction === 'desc' ? '-' : ''}${sort.columnId}` : null)

export function sortFromParam(param: string | null): SortState | null {
  if (!param) return null
  const desc = param.startsWith('-')
  const columnId = desc ? param.slice(1) : param
  return columnId ? { columnId, direction: desc ? 'desc' : 'asc' } : null
}

export const hasActiveFilters = ({ q, facets }: Pick<TxnFilters, 'q' | 'facets'>) => q.trim() !== '' || Object.values(facets).some((v) => v.length > 0)

export interface RowsCell {
  first: string | null
  /** The first value is a printed number, not a label. */
  mono: boolean
  /** Rows beyond the first one. */
  extra: number
}

/** What the «Partidas» column shows: the first printed number (or the exception or category) and how many more. */
export function rowsCell(row: TxnRow): RowsCell {
  const a = row.assignments[0]
  if (!a || row.rowCount === 0) return { first: null, mono: false, extra: 0 }
  const extra = row.rowCount - 1
  if (a.documentNumber) return { first: a.documentNumber, mono: true, extra }
  const label = a.exception ? exceptionLabel(a.exception) : a.category
  return { first: label, mono: false, extra }
}

/** The queue statuses first, then the closed ones. */
const statusRank = (s: CaseStatus) => {
  const i = INBOX_STATUSES.indexOf(s)
  return i >= 0 ? i : INBOX_STATUSES.length + (s === 'auto' ? 0 : 1)
}

export interface FacetOption {
  value: string
  label: string
  count?: number
}

/** Options of every facet come from the run and the package, never from fixed lists. */
export function buildFacetOptions(stats: RunStats | undefined, accounts: Account[] | undefined, entity: string | null): Record<FacetKey, FacetOption[]> {
  return {
    entity: (stats?.byEntity ?? []).map((e) => ({ value: e.entity, label: `${e.entity} · ${e.name}`, count: e.txns })),
    account: (accounts ?? []).filter((a) => !entity || a.entity === entity).map((a) => ({ value: a.accountId, label: `${a.accountId} · ${a.bank}`, count: a.txns })),
    rule: (stats?.byRule ?? []).map((r) => ({ value: r.rule, label: r.rule, count: r.txns })),
    exception: (stats?.byException ?? []).map((e) => ({ value: e.exception, label: exceptionLabel(e.exception) })),
    category: (stats?.byCategory ?? []).map((c) => ({ value: c.category, label: c.category, count: c.txns })),
    status: (Object.entries(stats?.byStatus ?? {}) as [CaseStatus, number][])
      .sort(([a], [b]) => statusRank(a) - statusRank(b))
      .map(([status, count]) => ({ value: status, label: CASE_STATUS_LABEL[status] ?? status, count })),
  }
}
