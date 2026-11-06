// Sample package and run for phase 0, until the real package arrives. Deterministic (seeded), no fake-data library.
// The package is emitted as files in the assumed format and goes through the same mappings as a real zip.
// The run stands in for the backend: it is hand-made, never computed by the frontend (CLAUDE.md §5).
// Planted issues, one per kind the challenge names (PROBLEM.md §5) plus a PO mismatch and an unmatched bank line.
import type { Alert, Match, ObjectRef, Run } from '@/domain'
import type { PackageFile } from '../build'

export const SAMPLE_PERIOD = '2026-09'
export const SAMPLE_NAME = 'Grupo Aurelia (muestra)'

function mulberry32(seed: number) {
  return () => {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const ENTITIES = [
  { id: '1000', name: 'Aurelia Holding, S.A.', country: 'ES', currency: 'EUR', taxId: 'A28000001', parentId: null, iban: 'ES7621000418401234567891', vat: 0.21 },
  { id: '1100', name: 'Aurelia Servicios, S.L.U.', country: 'ES', currency: 'EUR', taxId: 'B28000002', parentId: '1000', iban: 'ES9100492352082414205416', vat: 0.21 },
  { id: '2100', name: 'Aurelia Portugal, Lda.', country: 'PT', currency: 'EUR', taxId: 'PT509000003', parentId: '1000', iban: 'PT50000201231234567890154', vat: 0.23 },
  { id: '3100', name: 'Aurelia México, S.A. de C.V.', country: 'MX', currency: 'MXN', taxId: 'AME260101AB1', parentId: '1000', iban: 'MX12002180000000000018', vat: 0.16 },
]

const VENDOR_NAMES: [string, string][] = [
  ['1000', 'Despacho Lucena Abogados, S.L.P.'],
  ['1000', 'Nubaria Cloud Services, S.L.'],
  ['1000', 'Auditores Sierra & Asociados, S.L.'],
  ['1100', 'Limpiezas Orbe, S.L.'],
  ['1100', 'Suministros Eléctricos Vega, S.A.'],
  ['1100', 'Transportes Miravalle, S.L.'],
  ['1100', 'Seguridad Atalaya, S.A.'],
  ['1100', 'Papelería Montes, S.L.'],
  ['2100', 'Construções Ribeiro, Lda.'],
  ['2100', 'Energia Tejo, S.A.'],
  ['2100', 'Consultoria Alfama, Lda.'],
  ['3100', 'Materiales del Bajío, S.A. de C.V.'],
  ['3100', 'Logística Anáhuac, S.A. de C.V.'],
  ['3100', 'Servicios TI Querétaro, S.C.'],
]

/** Vendor whose IBAN is changed in the ERP two days before a payment to the new account. */
const SUSPICIOUS_VENDOR = 'V-1105'
const SUSPICIOUS_NEW_IBAN = 'LT601010012345678901'

const jsonl = (rows: object[]) => rows.map((r) => JSON.stringify(r)).join('\n') + '\n'
const day = (d: number) => `${SAMPLE_PERIOD}-${String(d).padStart(2, '0')}`
const ref = (kind: ObjectRef['kind'], id: string): ObjectRef => ({ kind, id })

export function samplePackage(): { files: PackageFile[]; run: Run } {
  const rnd = mulberry32(20261107)
  const int = (min: number, max: number) => min + Math.floor(rnd() * (max - min + 1))
  const entityOf = (id: string) => ENTITIES.find((e) => e.id === id)!

  const vendors = VENDOR_NAMES.map(([entityId, name], i) => {
    const e = entityOf(entityId)
    const id = `V-${entityId.slice(0, 2)}${String(i + 1).padStart(2, '0')}`
    const iban = `${e.country === 'MX' ? 'MX' : e.country}${String(int(10, 99))}${String(int(1e9, 9e9))}${String(int(1e9, 9e9))}`.slice(0, e.country === 'MX' ? 20 : 24)
    return { id, entityId, name, taxId: `${e.country}${int(10000000, 99999999)}`, iban, country: e.country, paymentTermsDays: [30, 45, 60][i % 3] }
  })
  const suspicious = vendors.find((v) => v.id === SUSPICIOUS_VENDOR)!
  const oldIban = suspicious.iban

  const contracts = vendors.slice(0, 6).map((v, i) => ({
    id: `CT-${v.entityId}-${String(i + 1).padStart(3, '0')}`,
    entityId: v.entityId,
    vendorId: v.id,
    title: ['Asesoría jurídica 2026', 'Hosting y licencias cloud', 'Auditoría de cuentas 2026', 'Limpieza de oficinas', 'Suministro eléctrico', 'Transporte de mercancías'][i],
    startDate: '2026-01-01',
    endDate: '2026-12-31',
    amountCents: int(30, 240) * 100_000,
    currency: entityOf(v.entityId).currency,
  }))

  const purchaseOrders = vendors.flatMap((v, i) =>
    [0, 1].map((k) => ({
      id: `PO-${v.entityId}-${String(i * 2 + k + 1).padStart(4, '0')}`,
      entityId: v.entityId,
      vendorId: v.id,
      contractId: contracts.find((c) => c.vendorId === v.id)?.id ?? null,
      date: `2026-08-${String(int(1, 28)).padStart(2, '0')}`,
      status: 'abierto',
      amountCents: int(8, 90) * 100_000 * (v.entityId === '3100' ? 18 : 1),
      currency: entityOf(v.entityId).currency,
    })),
  )

  type Inv = {
    id: string; entityId: string; vendorId: string; number: string; purchaseOrderId: string | null; issueDate: string; dueDate: string
    netCents: number; taxCents: number; taxRate: number; totalCents: number; currency: string; iban: string; status: string
  }
  const invoices: Inv[] = []
  vendors.forEach((v, vi) => {
    const e = entityOf(v.entityId)
    const pos = purchaseOrders.filter((p) => p.vendorId === v.id)
    for (let k = 0; k < 4; k++) {
      const po = pos[k % pos.length]
      const net = Math.round((po.amountCents / 4) * (0.6 + rnd() * 0.3))
      const tax = Math.round(net * e.vat)
      const issue = int(1, 22)
      invoices.push({
        id: `INV-${v.entityId}-${String(vi * 4 + k + 1).padStart(4, '0')}`,
        entityId: v.entityId,
        vendorId: v.id,
        number: `FA-2026-${String(int(100, 999)).padStart(4, '0')}`,
        purchaseOrderId: po.id,
        issueDate: day(issue),
        dueDate: day(Math.min(30, issue + 7)),
        netCents: net,
        taxCents: tax,
        taxRate: e.vat,
        totalCents: net + tax,
        currency: e.currency,
        iban: v.iban,
        status: 'pendiente',
      })
    }
  })

  // Planted: duplicate (same vendor and total, invoice number reformatted, received again by another channel).
  const original = invoices.find((i) => i.vendorId === 'V-1104')!
  const duplicate: Inv = { ...original, id: 'INV-1100-9001', number: original.number.replace(/-/g, ''), issueDate: day(Number(original.issueDate.slice(8)) + 3) }
  invoices.push(duplicate)
  // Planted: tax error (21 % stated, 10 % charged).
  const taxWrong = invoices.find((i) => i.vendorId === 'V-1003')!
  taxWrong.taxCents = Math.round(taxWrong.netCents * 0.1)
  taxWrong.totalCents = taxWrong.netCents + taxWrong.taxCents
  // Planted: invoice above its purchase order.
  const overPo = invoices.find((i) => i.vendorId === 'V-2110')!
  const po = purchaseOrders.find((p) => p.id === overPo.purchaseOrderId)!
  overPo.netCents = Math.round(po.amountCents * 1.18)
  overPo.taxCents = Math.round(overPo.netCents * overPo.taxRate)
  overPo.totalCents = overPo.netCents + overPo.taxCents
  // Planted: invoice of the suspicious vendor carrying the new IBAN.
  const ibanInvoice = invoices.find((i) => i.vendorId === SUSPICIOUS_VENDOR)!
  ibanInvoice.iban = SUSPICIOUS_NEW_IBAN
  // The vendor master is exported after the change: it already holds the new IBAN.
  suspicious.iban = SUSPICIOUS_NEW_IBAN

  const erpEvents = [
    ...invoices.slice(0, 18).map((inv, i) => ({
      id: `EV-${String(i + 1).padStart(4, '0')}`,
      entityId: inv.entityId,
      at: `${inv.issueDate}T09:${String(10 + i).padStart(2, '0')}:00+02:00`,
      user: ['mgarcia', 'jlopez', 'srodriguez'][i % 3],
      action: 'create',
      subjectKind: 'invoice',
      subjectId: inv.id,
      field: null,
      before: null,
      after: null,
    })),
    {
      id: 'EV-0901',
      entityId: suspicious.entityId,
      at: `${day(24)}T22:47:00+02:00`,
      user: 'proveedores.portal',
      action: 'update',
      subjectKind: 'vendor',
      subjectId: suspicious.id,
      field: 'iban',
      before: oldIban,
      after: SUSPICIOUS_NEW_IBAN,
    },
  ]

  // Bank: payments of most invoices, two customer receipts per entity, one fee per entity, one unknown receipt.
  type Tx = { id: string; entityId: string; accountIban: string; date: string; description: string; counterparty: string | null; counterpartyIban: string | null; amountCents: number; currency: string }
  const bank: Tx[] = []
  const ledger: object[] = []
  const matches: Match[] = []
  let line = 0
  let entry = 0
  const post = (entityId: string, date: string, description: string, sourceRef: string | null, currency: string, lines: [string, string, number, number][]) => {
    entry++
    const entryId = `AS-${entityId}-${String(entry).padStart(5, '0')}`
    const ids = lines.map(([account, accountName, debit, credit]) => {
      const id = `GL-${String(++line).padStart(6, '0')}`
      ledger.push({ id, entityId, entryId, date, account, accountName, description, debitCents: debit, creditCents: credit, currency, sourceRef })
      return id
    })
    return ids
  }
  const vendorName = (id: string) => vendors.find((v) => v.id === id)!.name

  for (const inv of invoices) {
    post(inv.entityId, inv.issueDate, `Factura ${inv.number} · ${vendorName(inv.vendorId)}`, inv.id, inv.currency, [
      ['62900000', 'Otros servicios', inv.netCents, 0],
      ['47200000', 'IVA soportado', inv.taxCents, 0],
      ['40000000', 'Proveedores', 0, inv.totalCents],
    ])
  }

  const paid = invoices.filter((i) => i !== duplicate && i !== taxWrong).filter((inv, k) => k % 5 !== 4 || inv === ibanInvoice)
  paid.forEach((inv, k) => {
    const e = entityOf(inv.entityId)
    const id = `BT-${inv.entityId}-${String(k + 1).padStart(4, '0')}`
    const date = day(Math.min(30, Number(inv.issueDate.slice(8)) + int(2, 8)))
    const toNewIban = inv === ibanInvoice
    bank.push({
      id,
      entityId: inv.entityId,
      accountIban: e.iban,
      date: toNewIban ? day(26) : date,
      description: `TRANSFERENCIA A ${vendorName(inv.vendorId).toUpperCase()} ${inv.number}`,
      counterparty: vendorName(inv.vendorId),
      counterpartyIban: toNewIban ? SUSPICIOUS_NEW_IBAN : inv.iban,
      amountCents: -inv.totalCents,
      currency: inv.currency,
    })
    const [glVendor] = post(inv.entityId, toNewIban ? day(26) : date, `Pago ${inv.number}`, id, inv.currency, [
      ['40000000', 'Proveedores', inv.totalCents, 0],
      ['57200000', 'Bancos', 0, inv.totalCents],
    ])
    const suggested = k % 11 === 7
    matches.push({
      bankTransactionId: id,
      status: suggested ? 'suggested' : 'matched',
      targets: [ref('ledgerEntry', glVendor), ref('invoice', inv.id)],
      confidence: suggested ? 0.74 : 0.98,
      rule: suggested ? 'BANK-AMOUNT-DATE-WINDOW' : 'BANK-EXACT-AMOUNT-REF',
      differenceCents: 0,
    })
  })

  ENTITIES.forEach((e, i) => {
    const mult = e.currency === 'MXN' ? 18 : 1
    for (let k = 0; k < 2; k++) {
      const id = `BT-${e.id}-R${k + 1}`
      const amount = int(20, 160) * 100_000 * mult
      const date = day(int(3, 28))
      bank.push({ id, entityId: e.id, accountIban: e.iban, date, description: `COBRO CLIENTE FRA. 2026/${int(100, 999)}`, counterparty: `Cliente ${i + 1}${k ? 'B' : 'A'}`, counterpartyIban: null, amountCents: amount, currency: e.currency })
      const [glBank] = post(e.id, date, 'Cobro de cliente', id, e.currency, [
        ['57200000', 'Bancos', amount, 0],
        ['43000000', 'Clientes', 0, amount],
      ])
      matches.push({ bankTransactionId: id, status: 'matched', targets: [ref('ledgerEntry', glBank)], confidence: 0.96, rule: 'BANK-EXACT-AMOUNT-REF', differenceCents: 0 })
    }
    const feeId = `BT-${e.id}-C1`
    const fee = int(15, 90) * 100 * mult
    bank.push({ id: feeId, entityId: e.id, accountIban: e.iban, date: day(30), description: 'COMISION MANTENIMIENTO CUENTA', counterparty: null, counterpartyIban: null, amountCents: -fee, currency: e.currency })
    matches.push({ bankTransactionId: feeId, status: 'unmatched', targets: [], confidence: null, rule: 'BANK-NO-CANDIDATE', differenceCents: -fee })
  })
  const mystery = { id: 'BT-1100-X1', entityId: '1100', accountIban: entityOf('1100').iban, date: day(29), description: 'TRANSFERENCIA RECIBIDA REF 88231', counterparty: null, counterpartyIban: 'ES0000000000000000088231', amountCents: 4_732_000, currency: 'EUR' }
  bank.push(mystery)
  matches.push({ bankTransactionId: mystery.id, status: 'unmatched', targets: [], confidence: null, rule: 'BANK-NO-CANDIDATE', differenceCents: mystery.amountCents })
  bank.sort((a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id))

  const suspiciousTx = bank.find((t) => t.counterpartyIban === SUSPICIOUS_NEW_IBAN)!
  const alerts: Alert[] = [
    {
      id: 'AL-001',
      type: 'bank_change',
      severity: 'high',
      entityId: suspicious.entityId,
      subject: ref('vendor', suspicious.id),
      amountCents: ibanInvoice.totalCents,
      currency: ibanInvoice.currency,
      title: 'IBAN del proveedor cambiado dos días antes de un pago',
      reason: `El IBAN pasó de ${oldIban} a ${SUSPICIOUS_NEW_IBAN} (cuenta lituana) el 24 de septiembre a las 22:47 desde el portal de proveedores. El 26 se pagó la factura ${ibanInvoice.number} a la cuenta nueva.`,
      rule: 'FRAUD-IBAN-CHANGE-BEFORE-PAYMENT',
      evidence: [ref('erpEvent', 'EV-0901'), ref('invoice', ibanInvoice.id), ref('bankTransaction', suspiciousTx.id)],
      action: 'Verificar el cambio con el proveedor por un canal conocido (teléfono de la ficha) y retener nuevos pagos hasta confirmarlo.',
    },
    {
      id: 'AL-002',
      type: 'duplicate',
      severity: 'high',
      entityId: duplicate.entityId,
      subject: ref('invoice', duplicate.id),
      amountCents: duplicate.totalCents,
      currency: duplicate.currency,
      title: 'Factura duplicada con el número reformateado',
      reason: `${duplicate.number} es ${original.number} sin guiones: mismo proveedor, mismo importe y fecha tres días posterior.`,
      rule: 'FRAUD-DUPLICATE-NORMALIZED-NUMBER',
      evidence: [ref('invoice', original.id), ref('vendor', duplicate.vendorId)],
      action: 'No contabilizar ni pagar la segunda factura.',
    },
    {
      id: 'AL-003',
      type: 'tax_error',
      severity: 'medium',
      entityId: taxWrong.entityId,
      subject: ref('invoice', taxWrong.id),
      amountCents: Math.round(taxWrong.netCents * 0.21) - taxWrong.taxCents,
      currency: taxWrong.currency,
      title: 'Cuota de IVA que no corresponde al tipo declarado',
      reason: 'La factura declara IVA al 21 %, pero la cuota es el 10 % de la base.',
      rule: 'TAX-RATE-TIMES-BASE',
      evidence: [ref('vendor', taxWrong.vendorId)],
      action: 'Pedir al proveedor una factura rectificativa antes de contabilizar.',
    },
    {
      id: 'AL-004',
      type: 'po_mismatch',
      severity: 'medium',
      entityId: overPo.entityId,
      subject: ref('invoice', overPo.id),
      amountCents: overPo.netCents - po.amountCents,
      currency: overPo.currency,
      title: 'Factura un 18 % por encima de su orden de compra',
      reason: `La base de la factura supera el importe de ${po.id} sin ampliación aprobada.`,
      rule: 'AP-INVOICE-WITHIN-PO',
      evidence: [ref('purchaseOrder', po.id)],
      action: 'Confirmar con el responsable de la compra antes de aprobar el pago.',
    },
    {
      id: 'AL-005',
      type: 'unmatched',
      severity: 'low',
      entityId: mystery.entityId,
      subject: ref('bankTransaction', mystery.id),
      amountCents: mystery.amountCents,
      currency: mystery.currency,
      title: 'Cobro sin factura ni cliente identificable',
      reason: 'Ninguna factura emitida ni apunte pendiente coincide en importe o referencia.',
      rule: 'BANK-NO-CANDIDATE',
      evidence: [],
      action: 'Identificar al pagador antes de registrar el cobro.',
    },
  ]

  const count = (s: Match['status']) => matches.filter((m) => m.status === s).length
  const fraudTypes = alerts.filter((a) => a.type === 'duplicate' || a.type === 'tax_error' || a.type === 'bank_change')
  const decisions = matches.length + invoices.length
  const review = count('suggested') + count('unmatched') + alerts.filter((a) => a.subject.kind === 'invoice').length
  const run: Run = {
    id: 'run-muestra-001',
    createdAt: '2026-11-06T18:00:00+01:00',
    period: SAMPLE_PERIOD,
    agent: { version: 'muestra', models: [], costUsd: null, durationMs: null },
    metrics: {
      accuracy: null,
      reconciliation: { matched: count('matched'), suggested: count('suggested'), unmatched: count('unmatched') },
      fraud: { detected: fraudTypes.length, byType: Object.fromEntries(fraudTypes.map((a) => [a.type, 1])) },
      autonomy: { auto: decisions - review, review },
      auditability: { withEvidence: decisions, total: decisions },
    },
    matches,
    alerts,
  }

  const files: PackageFile[] = [
    ['entities.jsonl', ENTITIES.map(({ iban: _iban, vat: _vat, ...e }) => e)],
    ['vendors.jsonl', vendors],
    ['contracts.jsonl', contracts],
    ['purchase_orders.jsonl', purchaseOrders],
    ['invoices.jsonl', invoices],
    ['bank_transactions.jsonl', bank],
    ['ledger.jsonl', ledger],
    ['erp_history.jsonl', erpEvents],
  ].map(([name, rows]) => {
    const text = jsonl(rows as object[])
    return { path: `muestra/${name as string}`, size: text.length, text }
  })
  return { files, run }
}
