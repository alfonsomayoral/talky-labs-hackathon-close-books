import type { Dataset, ObjectRef } from '@/domain'
import { KIND_OF } from '@/domain'
import { buildDataset } from '../build'
import { samplePackage } from './sample'

const meta = { name: 'muestra', period: '2026-09', source: 'fixtures' as const, loadedAt: '2026-11-06T18:00:00Z' }

function exists(ds: Dataset, r: ObjectRef): boolean {
  const kind = (Object.keys(KIND_OF) as (keyof typeof KIND_OF)[]).find((k) => KIND_OF[k] === r.kind)!
  return (ds[kind] as { id: string }[]).some((o) => o.id === r.id)
}

describe('sample package', () => {
  const { files, run } = samplePackage()
  const ds = buildDataset(files, meta)

  it('loads through the mappings without issues or unmapped files', () => {
    expect(ds.issues).toEqual([])
    expect(ds.unmapped).toEqual([])
    expect(ds.entities).toHaveLength(4)
    expect(ds.invoices.length).toBeGreaterThan(50)
    expect(ds.bankTransactions.length).toBeGreaterThan(40)
  })

  it('is deterministic', () => {
    expect(samplePackage().files).toEqual(files)
  })

  it('has balanced ledger entries', () => {
    const byEntry = new Map<string, number>()
    for (const l of ds.ledgerEntries) byEntry.set(l.entryId, (byEntry.get(l.entryId) ?? 0) + l.debitCents - l.creditCents)
    expect([...byEntry.values()].every((v) => v === 0)).toBe(true)
  })

  it('run references only objects of the dataset', () => {
    const refs = [...run.alerts.flatMap((a) => [a.subject, ...a.evidence]), ...run.matches.flatMap((m) => [{ kind: 'bankTransaction' as const, id: m.bankTransactionId }, ...m.targets])]
    expect(refs.filter((r) => !exists(ds, r))).toEqual([])
    expect(run.matches).toHaveLength(ds.bankTransactions.length)
  })

  it('plants the three issues the challenge names', () => {
    expect(new Set(run.alerts.map((a) => a.type))).toEqual(new Set(['bank_change', 'duplicate', 'tax_error', 'po_mismatch', 'unmatched']))
    const change = ds.erpEvents.find((e) => e.field === 'iban')!
    expect(ds.bankTransactions.some((t) => t.counterpartyIban === change.after && t.date > change.at.slice(0, 10))).toBe(true)
  })
})
