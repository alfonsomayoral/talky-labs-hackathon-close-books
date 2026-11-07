// Writes fixtures/run-sample/: a small synthetic run with the shapes of CONTRACT.md §2 and §5.1.
// Deterministic and with no data from db/ (which is never committed). `node mock/generate.mjs`
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'fixtures', 'run-sample')
const TXNS = 800
const RUN_ID = 'sample-20261107-010000'
const CREATED_AT = '2026-11-07T01:00:00+01:00'
const FROM = Date.UTC(2025, 6, 1)
const DAYS = 184

let seed = 20261107
const rnd = () => {
  seed = (seed * 1664525 + 1013904223) >>> 0
  return seed / 2 ** 32
}
const int = (min, max) => min + Math.floor(rnd() * (max - min + 1))
const pick = (list) => list[int(0, list.length - 1)]
const pad = (n, width) => String(n).padStart(width, '0')
const day = (offset) => new Date(FROM + offset * 86400000).toISOString().slice(0, 10)
const addDays = (date, n) => new Date(Date.parse(`${date}T00:00:00Z`) + n * 86400000).toISOString().slice(0, 10)

const ENTITIES = [
  { entity: 'ES00', name: 'Valtermia Industrial, S.A.', currency: 'EUR', rate: 1 },
  { entity: 'ES01', name: 'Valtermia Ibérica, S.L.', currency: 'EUR', rate: 1 },
  { entity: 'FR01', name: 'Valtermia France SAS', currency: 'EUR', rate: 1 },
  { entity: 'US01', name: 'Valtermia Americas Inc.', currency: 'USD', rate: 0.92 },
  { entity: 'MX01', name: 'Valtermia México S.A. de C.V.', currency: 'MXN', rate: 0.05 },
]
const ACCOUNTS = [
  { accountId: 'ES00-PENA-EUR', entity: 'ES00', bank: 'PENA', bankName: 'Banco Peñalara', currency: 'EUR', format: 'n43', purpose: 'Cabecera cash pooling / Pagos' },
  { accountId: 'ES01-PENA-EUR', entity: 'ES01', bank: 'PENA', bankName: 'Banco Peñalara', currency: 'EUR', format: 'n43', purpose: 'Cobros SEPA' },
  { accountId: 'ES01-MONC-EUR', entity: 'ES01', bank: 'MONC', bankName: 'Banco Moncayo', currency: 'EUR', format: 'n43', changesTo: 'camt053', purpose: 'Confirming' },
  { accountId: 'FR01-HPNB-EUR', entity: 'FR01', bank: 'HPNB', bankName: 'Hexagone Paribas', currency: 'EUR', format: 'camt053', purpose: 'Cobros y pagos' },
  { accountId: 'US01-LORV-USD', entity: 'US01', bank: 'LORV', bankName: 'Lorvan Bank', currency: 'USD', format: 'mt940', purpose: 'Lockbox' },
  { accountId: 'US01-WATT-USD', entity: 'US01', bank: 'WATT', bankName: 'Wattle Bank', currency: 'USD', format: 'camt053', purpose: 'ACH' },
  { accountId: 'MX01-UMVC-MXN', entity: 'MX01', bank: 'UMVC', bankName: 'Umbral Valores', currency: 'MXN', format: 'mt940', purpose: 'Cobros' },
  { accountId: 'ES01-VALD-EUR-2', entity: 'ES01', bank: 'VALD', bankName: null, currency: 'EUR', format: 'mt940', inMaster: false, purpose: null },
]

const NAMES = ['Wellness Lomaseca', 'Jardines Vicente', 'Piscinas Bailey', 'Suministros Prieto', 'Landscapes Santa Lucía', 'Química Urrutia', 'Talleres Otero', 'Ferretería Nieto', 'Hôtel Beauregard', 'Agua Clara', 'Riegos del Sur', 'Aquatech Norte', 'Pool & Spa Delta', 'Marina Levante', 'Viveros Arroyo', 'Cascada Azul', 'Termas del Valle', 'Spa Montecillo', 'Bombas Herrera', 'Filtros Roldán']
const SUFFIX = { ES00: 'S.L.', ES01: 'S.L.', FR01: 'SARL', US01: 'LLC', MX01: 'S.A. de C.V.' }

const parties = []
for (const e of ENTITIES) {
  const code = e.entity
  for (let i = 1; i <= 18; i++) {
    const group = i % 6 === 0 ? `G${code}${pad(i, 4)}` : null
    parties.push({
      partyId: `C${code}${pad(i, 6)}`, kind: 'customer', entity: code, name: `${pick(NAMES)} ${SUFFIX[code]}`, tradeName: null,
      type: pick(['KEY_ACCOUNT', 'SME', 'RETAIL']), country: code.slice(0, 2), taxId: `B${pad(int(0, 99999999), 8)}`, iban: `${code.slice(0, 2)}${pad(int(0, 99), 2)}${pad(int(0, 99999999), 8)}${pad(int(0, 99999999), 8)}`,
      paymentTerms: pick(['T30', 'T60', 'D2N30', 'DD15']), currency: e.currency, groupId: group, parentId: group && i > 6 ? `C${code}${pad(6, 6)}` : null, blockedSince: null,
    })
  }
  for (let i = 1; i <= 8; i++) {
    parties.push({
      partyId: `S${code}${pad(i, 6)}`, kind: 'supplier', entity: code, name: `${pick(['Suministros', 'Logística', 'Química', 'Servicios'])} ${pick(NAMES)} ${SUFFIX[code]}`, tradeName: null,
      type: pick(['GOODS', 'SERVICES']), country: code.slice(0, 2), taxId: `A${pad(int(0, 99999999), 8)}`, iban: null,
      paymentTerms: pick(['T30', 'T60']), currency: e.currency, groupId: null, parentId: null, blockedSince: null,
    })
  }
}
const partyById = new Map(parties.map((p) => [p.partyId, p]))
const partiesOf = (entity, kind) => parties.filter((p) => p.entity === entity && p.kind === kind)

// Items are created on demand, one per row of a movement, plus some left open at the end.
const items = []
let itemSeq = 0
function newItem(entity, party, cents, currency, issue) {
  itemSeq++
  const type = party.kind === 'customer' ? 'ARI' : 'API'
  const item = {
    itemId: `${type}-2025-${pad(itemSeq, 7)}`, itemType: type, entity, documentNumber: `${type === 'ARI' ? 'FV25-' : 'R25'}${pad(100000 + itemSeq, 7)}`,
    partyId: party.partyId, partyName: party.name, issueDate: issue, dueDate: addDays(issue, 30), currency, totalCents: cents,
    openAtStartCents: null, relatedDocument: null, reference: type === 'ARI' ? `PO${int(1000, 9999)}` : null,
  }
  items.push(item)
  return item
}

const RULES = [
  ['FILE-DD-BATCH', 0.24, 'directDebitBatch'], ['FILE-PAYMENT-RUN', 0.2, 'paymentRun'], ['FILE-CARD', 0.06, 'cardSettlement'], ['ADVICE-CSV', 0.1, 'remittanceAdvice'],
  ['REF-EXACT', 0.14, null], ['REF-NOPREFIX', 0.04, null], ['PARTY-AMOUNT', 0.1, 'customer'], ['HISTORY-DUPLICATE', 0.01, 'bankLine'], ['CAT-CODE', 0.07, null], ['FALLBACK-UNIDENTIFIED', 0.03, null], ['FALLBACK-CATEGORY', 0.01, null],
]
const pickRule = () => {
  let r = rnd()
  for (const rule of RULES) if ((r -= rule[1]) < 0) return rule
  return RULES[4]
}
const CATEGORIES = ['BANK_FEES', 'PAYROLL', 'TAX_PAYMENT', 'INTEREST_INCOME', 'LOAN_REPAYMENT', 'CASH_POOL', 'INSURANCE']
const DETAIL_DIR = { directDebitBatch: 'direct_debit_batches', paymentRun: 'payment_runs', cardSettlement: 'card_settlements' }

const txns = []
const explanations = []
const cases = []
const questions = []
const drafts = []
const documents = []
const facts = []
const detailRows = new Map()
const partyFacts = []
let caseQuestion = 0
let caseDraft = 0

function addCase(fields) {
  const c = {
    caseId: `CASE-${fields.bankTxnId}`, status: 'needs_review', priority: 2, partyId: null, itemIds: [], questionId: null, draftId: null, rule: null,
    suggestedAction: 'review', createdAt: CREATED_AT, ...fields,
  }
  cases.push(c)
  return c
}

function addDraft(c, party, kind, subject, body, attachments = []) {
  caseDraft++
  const draftId = `D-${pad(caseDraft, 6)}`
  drafts.push({
    draftId, caseId: c.caseId, kind, to: `administracion@${party.name.toLowerCase().normalize('NFD').replace(/[^a-z]/g, '').slice(0, 14)}.example`, toName: party.name, partyId: party.partyId,
    language: 'es', subject, body, attachments, generatedBy: 'claude-haiku-5-5', status: 'draft', createdAt: CREATED_AT,
  })
  c.draftId = draftId
}

for (let n = 0; n < TXNS; n++) {
  const account = pick(ACCOUNTS.filter((a) => a.inMaster !== false || rnd() < 0.2))
  const entity = ENTITIES.find((e) => e.entity === account.entity)
  const [rule, , sourceKind] = pickRule()
  const offset = int(0, DAYS - 1)
  const bookingDate = day(offset)
  const bankTxnId = `BT-2025-${pad(200000 + n, 7)}`
  const isCategory = rule === 'CAT-CODE' || rule === 'FALLBACK-CATEGORY'
  const isUnidentified = rule === 'FALLBACK-UNIDENTIFIED'
  const isPayment = rule === 'FILE-PAYMENT-RUN' || (isCategory && rnd() < 0.8) || (!isUnidentified && rnd() < 0.12)
  const partyKind = isPayment ? 'supplier' : 'customer'
  const party = isCategory || isUnidentified ? null : pick(partiesOf(entity.entity, partyKind))
  const rowsCount = isCategory || isUnidentified ? 0 : rule.startsWith('FILE') || rule.startsWith('ADVICE') ? int(2, 6) : 1
  const rows = []
  let total = 0
  for (let r = 0; r < Math.max(rowsCount, 1); r++) {
    const cents = int(4000, 480000)
    total += cents
    if (!rowsCount) {
      rows.push({ itemId: null, amountCents: null, currency: null, documentNumber: null, category: isUnidentified ? 'UNIDENTIFIED' : pick(CATEGORIES), exception: isUnidentified ? 'UNIDENTIFIED' : null })
      continue
    }
    const item = newItem(entity.entity, party, cents, entity.currency, addDays(bookingDate, -int(20, 70)))
    const exception = rule === 'HISTORY-DUPLICATE' ? 'DUPLICATE_PAYMENT' : rnd() < 0.08 ? pick(['SHORT_DISCOUNT', 'SHORT_DISPUTE', 'PARTIAL', 'FX_DIFFERENCE', 'SHORT_WITHHOLDING', 'SHORT_BANK_CHARGES', 'OVERPAYMENT', 'RETURNED']) : null
    rows.push({ itemId: item.itemId, amountCents: cents, currency: entity.currency, documentNumber: item.documentNumber, category: null, exception })
  }
  const amountCents = (isPayment ? -1 : 1) * total
  const amountEur = Math.round(amountCents * entity.rate)
  const payer = party?.name.toUpperCase() ?? pick(['MARIA VICENTE RUBIO', 'J. HERRERA GIL', 'COMERCIAL DEL ESTE', 'A. BEAUREGARD']);
  const firstNumber = rows[0].documentNumber
  const text = isCategory ? pick(['COMISION MANTENIMIENTO', 'NOMINA MES', 'IMPUESTO MOD 303', 'LIQUIDACION INTERESES', 'BARRIDO CASH POOL'])
    : rule === 'FILE-DD-BATCH' ? `REMESA RECIBOS ${pad(int(1000, 9999), 6)}`
    : rule === 'FILE-PAYMENT-RUN' ? `ORDEN PAGOS ${pad(int(1000, 9999), 6)}`
    : rule === 'FILE-CARD' ? `CARD SETTLEMENT MID ${int(100000000, 999999999)} ${rowsCount} TRX`
    : rule.startsWith('ADVICE') ? `TRF ${payer} AVISO ${int(1000000000, 9999999999)}`
    : isUnidentified ? `TRF ${payer}` : `TRF ${payer} ${firstNumber}`
  const line = {
    bankTxnId, accountId: account.accountId, entity: entity.entity, bank: account.bank, statementFormat: account.changesTo && offset > 92 ? account.changesTo : account.format,
    statementFile: `live/bank_statements/${account.accountId}/${account.accountId}_${bookingDate.slice(0, 7).replace('-', '')}.txt`, bookingDate, valueDate: bookingDate, amountCents, currency: entity.currency,
    bankCode: isCategory ? '17' : '02', bankSubcode: null, ref1: `${account.bank}${int(100000, 999999)}`, ref2: null, text, counterpartyName: party?.name ?? payer, counterpartyAccount: party?.iban ?? null,
    endToEndId: null, remittanceInfo: null, origAmountCents: null, origCurrency: null, amountEur, identified: rowsCount > 0,
  }
  txns.push(line)

  const confidence = rule === 'PARTY-AMOUNT' ? pick([0.7, 0.82, 0.95]) : isUnidentified || rule === 'FALLBACK-CATEGORY' ? 0 : 1
  const sources = []
  let reference = null
  if (sourceKind && DETAIL_DIR[sourceKind]) {
    const path = `${DETAIL_DIR[sourceKind]}/${entity.entity}_${bookingDate.slice(0, 7).replace('-', '')}_0.csv`
    sources.push({ kind: sourceKind, ref: path, label: path.split('/').pop() })
    reference = text
    const list = detailRows.get(path) ?? { kind: sourceKind, entity: entity.entity, month: bookingDate.slice(0, 7), rows: 0 }
    list.rows += rows.length
    detailRows.set(path, list)
  } else if (sourceKind === 'remittanceAdvice') {
    const path = `remittance_advices/${entity.entity}/RA_${bookingDate.replaceAll('-', '')}_${n}.csv`
    sources.push({ kind: 'remittanceAdvice', ref: path, label: path.split('/').pop() })
    reference = text.split('AVISO ')[1]
    documents.push({ path, kind: 'remittanceAdvice', entity: entity.entity, format: 'csv', name: path.split('/').pop(), date: bookingDate, partyName: party.name, text: `Aviso de remesa de ${party.name}\nFecha de pago: ${bookingDate}\n\n${rows.map((x) => `${x.documentNumber};${(x.amountCents / 100).toFixed(2)}`).join('\n')}` })
    rows.forEach((x, i) => facts.push({ docPath: path, lineNo: i + 1, documentNumber: x.documentNumber, documentNumberNorm: x.documentNumber.replace(/\D/g, ''), grossCents: x.amountCents, deductionCents: 0, reason: null, paidCents: x.amountCents, currency: x.currency, customerPo: null, voucher: null, clause: null, clauseValue: null, method: 'parser', model: null }))
  } else if (sourceKind === 'customer' && party) {
    sources.push({ kind: 'customer', ref: party.partyId, label: party.name })
  } else if (sourceKind === 'bankLine') {
    sources.push({ kind: 'bankLine', ref: txns[Math.max(0, n - 40)].bankTxnId })
  } else if (rule.startsWith('REF')) {
    reference = firstNumber
  }
  const candidateItems = isUnidentified ? [newItem(entity.entity, pick(partiesOf(entity.entity, 'customer')), total, entity.currency, day(Math.max(0, offset - 40))), newItem(entity.entity, pick(partiesOf(entity.entity, 'customer')), total, entity.currency, day(Math.max(0, offset - 25)))] : []
  const candidates = candidateItems.map((i) => ({ itemId: i.itemId, amountCents: i.totalCents, currency: i.currency, why: `Mismo importe, tercero ${i.partyName} sin relación con el ordenante` }))
  for (const row of rows) {
    explanations.push({ bankTxnId, itemId: row.itemId, documentNumber: row.documentNumber, amountCents: row.amountCents, currency: row.currency, category: row.category, exception: row.exception, rule, confidence, partyId: party?.partyId ?? null, reference, sources, candidates })
  }
  if (party) partyFacts.push({ bankTxnId, partyId: party.partyId, partyKind, payerName: payer, how: pick(['counterparty', 'iban', 'name', 'file']), confidence, alternatives: [] })

  // Cases, as CONTRACT.md §2.2: what did not close with confidence 1 by a file or a reference rule.
  const common = { bankTxnId, entity: entity.entity, amountCents: Math.abs(amountCents), currency: entity.currency, amountEur: Math.abs(amountEur), bookingDate, rule, partyId: party?.partyId ?? null, itemIds: rows.flatMap((x) => x.itemId ?? []) }
  const exception = rows.find((x) => x.exception && x.exception !== 'UNIDENTIFIED')?.exception
  const money = `${(Math.abs(amountCents) / 100).toFixed(2).replace('.', ',')} ${entity.currency}`
  if (isUnidentified) {
    caseQuestion++
    const questionId = `Q-${pad(caseQuestion, 6)}`
    const c = addCase({ ...common, kind: 'unidentified_receipt', status: 'question', priority: Math.abs(amountEur) > 100000 ? 1 : 2, suggestedAction: 'ask', questionId, summary: `Cobro de ${money} de ${payer} sin tercero ni referencia. Hay ${candidateItems.length} facturas abiertas con ese importe.` })
    questions.push({
      questionId, caseId: c.caseId, bankTxnId, entity: entity.entity, question: `¿A qué factura corresponde este cobro de ${money} de ${payer}?`,
      options: [...candidateItems.map((i) => ({ id: i.itemId, label: `${i.documentNumber} · ${money} · ${i.partyName} · vence ${i.dueDate}` })), { id: 'none', label: 'Ninguna: dejar como no identificado' }],
      defaultOption: 'none', rulePreview: { kind: 'payer_is_customer', payerName: payer, partyId: '<la opción elegida>', description: `En adelante, los cobros de ${payer} se asignan al cliente elegido` }, status: 'open', createdAt: CREATED_AT,
    })
  } else if (rule === 'FALLBACK-CATEGORY') {
    addCase({ ...common, kind: 'unknown_debit', status: 'fallback', priority: 3, summary: `Cargo de ${money} sin partida: «${text}». Categoría por código de banco.` })
  } else if (rule === 'HISTORY-DUPLICATE') {
    const c = addCase({ ...common, kind: 'duplicate_payment', status: 'needs_review', priority: 1, suggestedAction: partyKind === 'customer' ? 'email_customer' : 'email_supplier', summary: `${party.name} paga otra vez ${rows[0].documentNumber}, ya liquidada. Hay ${money} a devolver.` })
    addDraft(c, party, partyKind === 'customer' ? 'email_customer' : 'email_supplier', `Pago duplicado de la factura ${rows[0].documentNumber}`, `Estimados señores:\n\nHemos recibido dos pagos de la factura ${rows[0].documentNumber} por ${money}. Les proponemos devolver el segundo o compensarlo en su próxima remesa.\n\nQuedamos a la espera de su confirmación.\n\nUn saludo,\nTesorería de ${entity.name}`, [{ kind: 'pdf', ref: `pdfs/${entity.entity}/${rows[0].itemId}.pdf`, label: rows[0].documentNumber }])
  } else if (rule === 'PARTY-AMOUNT' && confidence < 0.9) {
    addCase({ ...common, kind: 'ambiguous_match', status: 'needs_review', priority: 2, summary: `Casado con ${party.name} por tercero e importe (confianza ${Math.round(confidence * 100)} %). Conviene revisarlo.` })
  } else if (partyKind === 'supplier' && exception) {
    const c = addCase({ ...common, kind: 'supplier_invoice_mismatch', status: 'needs_review', priority: int(1, 2), suggestedAction: 'email_supplier', summary: `La remesa paga ${rows[0].documentNumber} de ${party.name} por un importe distinto al documento (${exception}).` })
    addDraft(c, party, 'email_supplier', `Diferencia en la factura ${rows[0].documentNumber}`, `Estimados señores:\n\nEl pago de la factura ${rows[0].documentNumber} no coincide con el importe del documento. ¿Pueden emitir el abono correspondiente?\n\nUn saludo,\nCuentas a pagar de ${entity.name}`)
  } else if (exception === 'SHORT_DISPUTE') {
    const c = addCase({ ...common, kind: 'dispute', status: 'needs_review', priority: 1, suggestedAction: 'email_customer', summary: `${party.name} descuenta parte de ${rows[0].documentNumber} con motivo de disputa.` })
    addDraft(c, party, 'email_customer', `Disputa en la factura ${rows[0].documentNumber}`, `Estimados señores:\n\nHemos recibido su pago de la factura ${rows[0].documentNumber} con una deducción. ¿Pueden indicarnos el motivo y adjuntar la documentación?\n\nUn saludo,\nTesorería de ${entity.name}`)
  } else if (exception === 'RETURNED') {
    addCase({ ...common, kind: 'returned', status: 'auto', priority: 3, suggestedAction: 'none', summary: `Recibo devuelto de ${party.name}: la partida ${rows[0].documentNumber} se reabre.` })
  } else if (exception === 'FX_DIFFERENCE') {
    addCase({ ...common, kind: 'fx_difference', status: 'auto', priority: 3, suggestedAction: 'none', summary: `Diferencia de cambio en ${rows[0].documentNumber}: dentro de tolerancia.` })
  } else if (exception === 'PARTIAL') {
    addCase({ ...common, kind: 'short_payment', status: 'needs_review', priority: 2, summary: `${party.name} paga una parte de ${rows[0].documentNumber} sin explicar el resto.` })
  }
}

// Open at the end of the phase: overdue customers (aggregate cases) and the rest of the ledger.
const asOf = day(DAYS - 1)
const openItems = items.map((item, i) => {
  const explained = explanations.filter((e) => e.itemId === item.itemId)
  const open = explained.length === 0 ? item.totalCents : explained[0].exception === 'PARTIAL' ? Math.round(item.totalCents / 2) : 0
  const entity = ENTITIES.find((e) => e.entity === item.entity)
  const daysOverdue = open > 0 && item.dueDate < asOf ? Math.round((Date.parse(asOf) - Date.parse(item.dueDate)) / 86400000) : 0
  return {
    itemId: item.itemId, itemType: item.itemType, entity: item.entity, partyId: item.partyId, partyName: item.partyName, documentNumber: item.documentNumber, issueDate: item.issueDate, dueDate: item.dueDate, currency: item.currency,
    totalCents: item.totalCents, openAtStartCents: i % 9 === 0 ? item.totalCents : 0, appliedCents: item.totalCents - open, openAtEndCents: open, openAtEndEur: Math.round(open * entity.rate),
    status: open === 0 ? 'cleared' : open < item.totalCents ? 'partial' : 'open', daysOverdue,
    history: explained.map((e) => ({ bankTxnId: e.bankTxnId, bookingDate: txns.find((t) => t.bankTxnId === e.bankTxnId).bookingDate, amountCents: e.amountCents, exception: e.exception })),
  }
})
for (let i = 0; i < 180; i++) {
  const entity = pick(ENTITIES)
  const party = pick(partiesOf(entity.entity, rnd() < 0.8 ? 'customer' : 'supplier'))
  const cents = int(8000, 900000)
  const issue = day(int(0, DAYS - 20) - 40)
  const item = newItem(entity.entity, party, cents, entity.currency, issue)
  const daysOverdue = item.dueDate < asOf ? Math.round((Date.parse(asOf) - Date.parse(item.dueDate)) / 86400000) : 0
  openItems.push({ ...item, relatedDocument: undefined, reference: undefined, openAtStartCents: cents, appliedCents: 0, openAtEndCents: cents, openAtEndEur: Math.round(cents * entity.rate), status: i % 13 === 0 ? 'disputed' : 'open', daysOverdue, history: [] })
}
const overdue = new Map()
for (const item of openItems) {
  if (item.itemType !== 'ARI' || item.daysOverdue <= 0) continue
  const o = overdue.get(item.partyId) ?? { eur: 0, itemIds: [], entity: item.entity, currency: item.currency, documents: [] }
  o.eur += item.openAtEndEur
  o.itemIds.push(item.itemId)
  o.documents.push(item)
  overdue.set(item.partyId, o)
}
let overdueCases = 0
for (const [partyId, o] of [...overdue].sort((a, b) => b[1].eur - a[1].eur).slice(0, 14)) {
  const party = partyById.get(partyId)
  overdueCases++
  const c = addCase({
    bankTxnId: null, caseId: `CASE-overdue_customer-${overdueCases}`, kind: 'overdue_customer', status: 'needs_review', priority: overdueCases <= 4 ? 1 : 2, entity: o.entity, partyId, itemIds: o.itemIds, amountCents: o.eur, currency: 'EUR', amountEur: o.eur, bookingDate: null,
    suggestedAction: 'email_customer', summary: `${party.name} tiene ${o.itemIds.length} facturas vencidas por ${(o.eur / 100).toFixed(2).replace('.', ',')} EUR.`,
  })
  addDraft(c, party, 'email_customer', 'Facturas vencidas pendientes de pago', `Estimados señores:\n\nA fecha de hoy constan vencidas las siguientes facturas:\n\n${o.documents.slice(0, 6).map((d) => `· ${d.documentNumber}, vencida el ${d.dueDate}`).join('\n')}\n\nLes rogamos que nos indiquen la fecha prevista de pago.\n\nUn saludo,\nTesorería`, o.documents.slice(0, 3).map((d) => ({ kind: 'pdf', ref: `pdfs/${d.entity}/${d.itemId}.pdf`, label: d.documentNumber })))
}
for (const item of items.slice(0, 120)) {
  const path = `pdfs/${item.entity}/${item.itemId}.pdf`
  documents.push({ path, kind: 'invoicePdf', entity: item.entity, format: 'pdf', name: `${item.itemId}.pdf`, date: item.issueDate, partyName: item.partyName, text: `FACTURA ${item.documentNumber}\n${item.partyName}\nFecha ${item.issueDate} · Vencimiento ${item.dueDate}\nTotal ${(item.totalCents / 100).toFixed(2)} ${item.currency}` })
}

// The six kinds of memory rule of CONTRACT.md §4, in turn, so every question flow can be walked. No rnd() here: the rest of the run stays as it is.
questions.forEach((q, i) => {
  const c = cases.find((x) => x.caseId === q.caseId)
  const customer = partiesOf(q.entity, 'customer')[i % 18]
  const supplier = partiesOf(q.entity, 'supplier')[i % 8]
  const payer = txns.find((t) => t.bankTxnId === q.bankTxnId).counterpartyName
  q.rulePreview = [
    { kind: 'payer_is_customer', payerName: payer, partyId: '<la opción elegida>', description: `En adelante, los cobros de ${payer} se asignan al cliente elegido` },
    { kind: 'reference_alias', pattern: `REF-${1000 + i}`, documentNumber: '<la opción elegida>', description: `En adelante, la referencia REF-${1000 + i} apunta a la factura elegida` },
    { kind: 'parent_pays', payerPartyId: customer.partyId, forPartyId: '<la opción elegida>', description: `En adelante, ${customer.name} paga por el cliente elegido` },
    { kind: 'ignore_suffix', partyId: customer.partyId, regex: '-[A-Z]{2}$', description: `En adelante, se ignora el sufijo de país en las referencias de ${customer.name}` },
    { kind: 'supplier_nets_credit_notes', partyId: supplier.partyId, description: `En adelante, ${supplier.name} neta sus abonos en sus cobros` },
    { kind: 'always_category', bank: 'PENA', bankCode: '17', textPattern: 'TRASPASO', category: 'INTERNAL_TRANSFER', description: 'En adelante, los apuntes «TRASPASO» de Banco Peñalara son traspasos internos' },
  ][i % 6]
  c.partyId = null
})

const count = (list, key) => list.reduce((acc, x) => ((acc[key(x)] = (acc[key(x)] ?? 0) + 1), acc), {})
const dropNull = (o) => Object.fromEntries(Object.entries(o).filter(([k]) => k !== 'null' && k !== 'undefined'))
const run = {
  runId: RUN_ID, phase: 'sample', dataDir: 'fixtures/run-sample', createdAt: CREATED_AT, gitCommit: 'a286f42', durationMs: 241000,
  stages: { load: 12000, index: 8000, documents: 90000, rules: 70000, resolve: 30000, output: 31000 }, txns: txns.length, rows: explanations.length,
  byRule: count(explanations, (e) => e.rule), byException: dropNull(count(explanations, (e) => e.exception)), byCategory: dropNull(count(explanations, (e) => e.category)), cases: count(cases, (c) => c.status),
  models: { 'claude-haiku-5-5': { calls: 812, inputTokens: 1200000, outputTokens: 90000, costUsd: 0.4 } }, memoryRulesApplied: 0,
  score: { score: 71.4, metrics: { allocation_f1: 0.78, precision: 0.97, recall: 0.65, txn_accuracy: 0.69, exception_macro_f1: 0.55, amount_weighted_accuracy: 0.74, rows: 3100, txns_covered: 1400, txns_total: 1400 }, segments: { ar_1to1: { n: 320, accuracy: 0.96 }, ar_ref_noise: { n: 410, accuracy: 0.52 }, ap_payment_multi: { n: 280, accuracy: 0.91 }, ar_dd_batch: { n: 230, accuracy: 0.99 }, nonitem_bank_fees: { n: 160, accuracy: 0.88 } } },
}

const accounts = ACCOUNTS.map(({ format, changesTo, ...a }) => ({
  ...a, iban: a.inMaster === false ? null : `${a.entity.slice(0, 2)}00${pad(int(0, 99999999), 8)}${pad(int(0, 99999999), 8)}`, inMaster: a.inMaster !== false,
  formats: changesTo ? [{ format, from: day(0), to: '2025-09-30' }, { format: changesTo, from: '2025-10-01', to: null }] : [{ format, from: day(0), to: null }],
}))
const detailFiles = [...detailRows].map(([path, f]) => ({ path, ...f }))

mkdirSync(OUT, { recursive: true })
const jsonl = (name, rows) => writeFileSync(join(OUT, name), rows.map((r) => JSON.stringify(r)).join('\n') + '\n')
writeFileSync(join(OUT, 'run.json'), JSON.stringify(run, null, 1))
writeFileSync(join(OUT, 'masters.json'), JSON.stringify({ entities: ENTITIES.map(({ entity, name }) => ({ entity, name })), rates: Object.fromEntries(ENTITIES.map((e) => [e.currency, e.rate])), accounts }))
jsonl('transactions.jsonl', txns)
jsonl('explanations.jsonl', explanations)
jsonl('cases.jsonl', cases)
jsonl('questions.jsonl', questions)
jsonl('drafts.jsonl', drafts)
jsonl('open_items.jsonl', openItems)
jsonl('parties.jsonl', parties)
jsonl('party_facts.jsonl', partyFacts)
jsonl('items.jsonl', items)
jsonl('documents.jsonl', documents)
jsonl('document_facts.jsonl', facts)
jsonl('detail_files.jsonl', detailFiles)
console.log(`${txns.length} movimientos, ${explanations.length} filas, ${cases.length} casos, ${questions.length} preguntas, ${drafts.length} borradores, ${openItems.length} partidas`)
