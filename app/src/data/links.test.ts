import { buildDataset } from './build'
import { samplePackage } from './fixtures/sample'
import { buildLinks, parseRefKey } from './links'

const { files, run } = samplePackage()
const ds = buildDataset(files, { name: 'm', period: '2026-09', source: 'fixtures', loadedAt: '' })
const links = buildLinks(ds, run)

it('relates an invoice to its vendor, order, ledger lines and payment', () => {
  const inv = ds.invoices[0]
  const payment = run.matches.find((m) => m.targets.some((t) => t.kind === 'invoice' && t.id === inv.id))
  const kinds = links.related({ kind: 'invoice', id: inv.id }).map((r) => r.kind)
  expect(kinds).toEqual(expect.arrayContaining(['vendor', 'purchaseOrder', 'ledgerEntry']))
  if (payment) expect(kinds).toContain('bankTransaction')
})

it('finds the IBAN change in the vendor history and its alert', () => {
  const vendor = { kind: 'vendor' as const, id: 'V-1105' }
  expect(links.historyOf(vendor).map((e) => e.field)).toEqual(['iban'])
  expect(links.alertsOf(vendor).map((a) => a.type)).toEqual(['bank_change'])
})

it('parses object keys and rejects unknown kinds', () => {
  expect(parseRefKey('invoice:INV:1')).toEqual({ kind: 'invoice', id: 'INV:1' })
  expect(parseRefKey('spaceship:X')).toBeNull()
})
