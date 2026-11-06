// Counts of the run's bank matches per entity. Aggregation only: the matches themselves come from the backend.
import type { Dataset, MatchStatus, Run } from '@/domain'

export type MatchCounts = Record<MatchStatus, number> & { total: number }

const empty = (): MatchCounts => ({ matched: 0, suggested: 0, unmatched: 0, total: 0 })

export function matchCountsByEntity(dataset: Dataset, run: Run | null): Map<string, MatchCounts> {
  const entityOf = new Map(dataset.bankTransactions.map((t) => [t.id, t.entityId]))
  const out = new Map(dataset.entities.map((e) => [e.id, empty()]))
  for (const m of run?.matches ?? []) {
    const entity = entityOf.get(m.bankTransactionId)
    if (!entity) continue
    const c = out.get(entity) ?? empty()
    c[m.status]++
    c.total++
    out.set(entity, c)
  }
  return out
}

export function sumCounts(counts: Iterable<MatchCounts>): MatchCounts {
  const total = empty()
  for (const c of counts) {
    total.matched += c.matched
    total.suggested += c.suggested
    total.unmatched += c.unmatched
    total.total += c.total
  }
  return total
}
