// Pure logic of Cobros: the risk label, search over the 200 customers the API returns, and sort in the URL.
import type { AgingParty } from '@/domain'
import type { SortState } from '@/components'

export type Risk = 'high' | 'medium' | 'low'

export const RISK_LABEL: Record<Risk, string> = { high: 'Alto', medium: 'Medio', low: 'Bajo' }

export const RISK_EMPHASIS = { high: 'strong', medium: 'medium', low: 'quiet' } as const

export const RISK_HEURISTIC =
  'Heurística de esta pantalla, no un dato del paquete: alto si más de la mitad del saldo lleva más de 60 días o hay más de una disputa; medio si hay saldo de más de 30 días; bajo en el resto.'

/**
 * A heuristic of this screen, not a field of the package: high with more than half of the balance past 60 days
 * or more than one open dispute; medium with any balance past 30 days; low otherwise.
 */
export function riskOf(p: AgingParty): Risk {
  const { d31_60, d61_90, d90_plus } = p.buckets
  const past60 = d61_90 + d90_plus
  if (p.disputes > 1 || (p.openEur > 0 && past60 / p.openEur > 0.5)) return 'high'
  if (d31_60 + past60 > 0) return 'medium'
  return 'low'
}

const plain = (s: string) => s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()

export function filterParties(parties: AgingParty[], q: string | null): AgingParty[] {
  const needle = q ? plain(q.trim()) : ''
  if (!needle) return parties
  return parties.filter((p) => plain(`${p.partyName} ${p.partyId} ${p.entity}`).includes(needle))
}

const SORT_FIELDS = ['partyName', 'entity', 'overdueEur', 'openItems', 'oldestDaysOverdue', 'disputes', 'duplicates', 'risk']

export function sortFromParam(param: string | null): SortState | null {
  if (!param) return null
  const desc = param.startsWith('-')
  const columnId = desc ? param.slice(1) : param
  return SORT_FIELDS.includes(columnId) ? { columnId, direction: desc ? 'desc' : 'asc' } : null
}

export const sortToParam = (sort: SortState | null) => (sort ? `${sort.direction === 'desc' ? '-' : ''}${sort.columnId}` : null)

/** The customers that can be chased first, each group in the order it came. */
export const chaseFirst = (parties: AgingParty[]): AgingParty[] => [...parties.filter((p) => p.caseId), ...parties.filter((p) => !p.caseId)]
