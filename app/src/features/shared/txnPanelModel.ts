// Pure logic of the movement panel.
import type { DetailRow } from '@/domain'

/** Per currency: amounts of different currencies are never added. */
export function sumByCurrency(rows: Pick<DetailRow, 'amountCents' | 'currency'>[]): { currency: string; cents: number }[] {
  const totals = new Map<string, number>()
  for (const r of rows) {
    if (r.amountCents == null || !r.currency) continue
    totals.set(r.currency, (totals.get(r.currency) ?? 0) + r.amountCents)
  }
  return [...totals].map(([currency, cents]) => ({ currency, cents }))
}

/** The rules that produced the rows of a movement and the least certain confidence among them. */
export function decisionOf(rows: Pick<DetailRow, 'rule' | 'confidence'>[]): { rules: string[]; confidence: number | null } {
  return {
    rules: [...new Set(rows.map((r) => r.rule))],
    confidence: rows.length ? Math.min(...rows.map((r) => r.confidence)) : null,
  }
}

/** Parties settled by the movement's rows. More than one in a payment run or a batch. */
export const distinctParties = (rows: Pick<DetailRow, 'item'>[]) => new Set(rows.flatMap((r) => r.item?.partyId ?? [])).size
