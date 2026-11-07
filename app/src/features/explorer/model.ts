// Pure logic of the explorer: URL state and small derivations.
import { formatDate, formatNumber } from '@/lib/format'
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
  return extras
}

/** What a clause extracted from a document says. */
export function clauseText(clause: string, value: Record<string, unknown> | null | undefined): string {
  const v = (value ?? {}) as {
    n?: number
    days?: number[]
    pct?: number
    releaseDate?: string
    proforma?: string
    replaces?: string
    month?: string
    year?: number
    mode?: string
    quarter?: number
    factor?: string
    iban?: string
    from?: string
  }
  switch (clause) {
    case 'instalments':
      return `Pago en ${v.n} plazos a ${v.days?.join('/')} días`
    case 'retention':
      return `Retención de garantía del ${formatNumber(v.pct)} %, se libera el ${formatDate(v.releaseDate)}`
    case 'advance_deduction':
      return `Deduce el anticipo de la proforma ${v.proforma}`
    case 'replaces':
      return `Anula y sustituye a ${v.replaces}`
    case 'service_month':
      return `Mes de servicio: ${v.month} ${v.year}`
    case 'credit_refund':
      return v.mode === 'refund' ? 'El abono se reembolsa por transferencia' : 'El abono se compensa en próximos pagos'
    case 'rappel_offset':
      return `Rappel del T${v.quarter} de ${v.year} (${formatNumber(v.pct)} %), a compensar`
    case 'rappel_payout':
      return `Rappel del T${v.quarter} de ${v.year} (${formatNumber(v.pct)} %), a pagar`
    case 'factored':
      return `Cedida a ${v.factor}`
    case 'new_iban':
      return `Nueva cuenta ${v.iban} desde el ${formatDate(v.from)}`
    default:
      return `Cláusula ${clause}`
  }
}
