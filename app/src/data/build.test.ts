import { buildDataset } from './build'

const meta = { name: 'test', period: null, source: 'zip' as const, loadedAt: '2026-11-07T10:00:00Z' }

describe('buildDataset', () => {
  it('maps a known file by name, decimal or cents amounts alike', () => {
    const ds = buildDataset(
      [
        {
          path: 'pkg/facturas.csv',
          size: 1,
          text: 'id;entity_id;vendor_id;number;issue_date;net;tax;total;currency\nF1;1000;V1;A-1;2026-09-03;1.000,00;210,00;1.210,00;EUR',
        },
        {
          path: 'pkg/vendors.jsonl',
          size: 1,
          text: '{"id":"V1","entityId":"1000","name":"Acme","iban":"ES12"}',
        },
      ],
      meta,
    )
    expect(ds.invoices).toHaveLength(1)
    expect(ds.invoices[0]).toMatchObject({ id: 'F1', netCents: 100000, taxCents: 21000, totalCents: 121000, purchaseOrderId: null })
    expect(ds.vendors[0]).toMatchObject({ id: 'V1', iban: 'ES12' })
    expect(ds.issues).toEqual([])
  })

  it('keeps a bad row as an issue and loads the rest', () => {
    const ds = buildDataset(
      [{ path: 'invoices.jsonl', size: 1, text: '{"id":"F1"}\n{"id":"F2","entityId":"1","vendorId":"V","number":"2","issueDate":"2026-09-01","netCents":100,"taxCents":21,"totalCents":121,"currency":"EUR"}' }],
      meta,
    )
    expect(ds.invoices.map((i) => i.id)).toEqual(['F2'])
    expect(ds.issues).toEqual([{ path: 'invoices.jsonl', row: 1, message: 'Falta el campo entityId' }])
  })

  it('keeps unknown and binary files as unmapped, with a preview when tabular', () => {
    const ds = buildDataset(
      [
        { path: 'misc/fx_rates.csv', size: 10, text: 'date,rate\n2026-09-01,1.1' },
        { path: 'docs/F1.pdf', size: 99, text: null },
      ],
      meta,
    )
    expect(ds.unmapped).toEqual([
      { path: 'misc/fx_rates.csv', size: 10, preview: [{ date: '2026-09-01', rate: '1.1' }] },
      { path: 'docs/F1.pdf', size: 99, preview: null },
    ])
  })

  it('rejects an ERP event about an unknown kind of object', () => {
    const ds = buildDataset(
      [{ path: 'erp_history.jsonl', size: 1, text: '{"id":"E1","entityId":"1","at":"2026-09-01T10:00:00Z","action":"update","subjectKind":"spaceship","subjectId":"X"}' }],
      meta,
    )
    expect(ds.erpEvents).toEqual([])
    expect(ds.issues[0].message).toMatch(/desconocido/)
  })
})
