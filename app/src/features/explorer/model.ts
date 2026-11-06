// Pure logic of the explorer: URL state and small derivations.
import type { DocumentFact } from '@/domain'
import type { SortState } from '@/components'

/** `field` or `-field` (CONTRACT.md §5.1); the column id is the field of the row. */
export const toSortParam = (sort: SortState | null) => (sort ? `${sort.direction === 'desc' ? '-' : ''}${sort.columnId}` : null)

export function fromSortParam(param: string | null): SortState | null {
  if (!param) return null
  const desc = param.startsWith('-')
  const columnId = desc ? param.slice(1) : param
  return columnId ? { columnId, direction: desc ? 'desc' : 'asc' } : null
}

/** Another type is another list: only the run and the entity scope survive. */
export function switchTab(params: URLSearchParams, tipo: string): URLSearchParams {
  const next = new URLSearchParams()
  for (const name of ['run', 'sociedad']) {
    const value = params.get(name)
    if (value) next.set(name, value)
  }
  next.set('tipo', tipo)
  return next
}

/** A scoped link (`useScopedTo`) plus the params that open something on its page. */
export function withParams(to: { pathname: string; search: string }, params: Record<string, string>) {
  const search = new URLSearchParams(to.search)
  for (const [name, value] of Object.entries(params)) search.set(name, value)
  return { pathname: to.pathname, search: `?${search}` }
}

/** What a remittance line says besides its amounts. */
export function factExtras(fact: DocumentFact): string[] {
  const extras: string[] = []
  if (fact.customerPo) extras.push(`Pedido ${fact.customerPo}`)
  if (fact.voucher) extras.push(`Voucher ${fact.voucher}`)
  if (fact.clause) extras.push(`Cláusula ${fact.clause}${fact.clauseValue ? ` ${JSON.stringify(fact.clauseValue)}` : ''}`)
  return extras
}
