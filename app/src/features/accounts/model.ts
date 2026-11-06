// Pure logic of the accounts screen.
import type { Account } from '@/domain'
import { formatMonth } from '@/lib/format'

type Periods = Account['formats']

const byStart = (formats: Periods) => [...formats].sort((a, b) => a.from.localeCompare(b.from))

/** Format of the open period (or the latest one). */
export function currentFormat(formats: Periods): string | null {
  return byStart(formats).at(-1)?.format ?? null
}

/** «n43 → camt053 desde oct 2025» when the statement format changed along the phase (the drift), else null. */
export function formatChange(formats: Periods): string | null {
  const chain: { format: string; from: string }[] = []
  for (const p of byStart(formats)) if (chain.at(-1)?.format !== p.format) chain.push(p)
  if (chain.length < 2) return null
  return `${chain.map((p) => p.format).join(' → ')} desde ${formatMonth(chain.at(-1)!.from)}`
}

export function summarize(accounts: Account[]) {
  return {
    accounts: accounts.length,
    banks: new Set(accounts.map((a) => a.bank)).size,
    formatChanges: accounts.filter((a) => formatChange(a.formats) != null).length,
  }
}

export const filterByEntity = (accounts: Account[], entity: string | null) => (entity ? accounts.filter((a) => a.entity === entity) : accounts)
