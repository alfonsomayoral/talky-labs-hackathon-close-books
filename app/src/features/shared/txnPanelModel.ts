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

/** The party of the items when there is exactly one: the movement may have no resolved payer and still settle one party. */
export function soleParty(rows: Pick<DetailRow, 'item'>[]): { partyId: string; partyName: string | null } | null {
  const item = rows.find((r) => r.item)?.item
  return item && distinctParties(rows) === 1 ? { partyId: item.partyId, partyName: item.partyName ?? null } : null
}

/** Cents as the delivered CSV writes them: dot decimals, no thousands. */
const csvAmount = (cents: number) => `${cents < 0 ? '-' : ''}${Math.floor(Math.abs(cents) / 100)}.${String(Math.abs(cents) % 100).padStart(2, '0')}`

/** The movement's lines of the delivered CSV (FORMAT.md), header first. */
export function submissionLines(bankTxnId: string, rows: Pick<DetailRow, 'itemId' | 'amountCents' | 'category' | 'exception'>[]): string[] {
  return ['bank_txn_id,item_id,amount,category,exception', ...rows.map((r) => [bankTxnId, r.itemId ?? '', r.amountCents == null ? '' : csvAmount(r.amountCents), r.category ?? '', r.exception ?? ''].join(','))]
}
