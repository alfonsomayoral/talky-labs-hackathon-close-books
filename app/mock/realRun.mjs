// Reads a real run folder (CONTRACT.md §2) and its phase in db/, for the mock to serve until `closebooks serve`
// exists. Parquet is not read: parties come from the explanations and open items are recomputed from them.
import { createReadStream, existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { createInterface } from 'node:readline'
import { createGunzip, gunzipSync } from 'node:zlib'

/** RFC 4180 fields of one line: the package's CSVs have no embedded newlines. */
function splitCsv(line) {
  if (!line.includes('"')) return line.split(',')
  const out = []
  let field = ''
  let quoted = false
  for (let i = 0; i < line.length; i++) {
    const c = line[i]
    if (quoted) {
      if (c === '"' && line[i + 1] === '"') (field += '"'), i++
      else if (c === '"') quoted = false
      else field += c
    } else if (c === '"') quoted = true
    else if (c === ',') out.push(field), (field = '')
    else field += c
  }
  out.push(field)
  return out
}

async function eachCsv(path, onRow) {
  if (!existsSync(path)) return
  const stream = path.endsWith('.gz') ? createReadStream(path).pipe(createGunzip()) : createReadStream(path)
  let header = null
  for await (const line of createInterface({ input: stream, crlfDelay: Infinity })) {
    if (!line) continue
    const fields = splitCsv(line)
    if (!header) {
      header = fields
      continue
    }
    const row = {}
    for (let i = 0; i < header.length; i++) row[header[i]] = fields[i] ?? ''
    onRow(row)
  }
}

const cents = (s) => (s ? Math.round(Number(s) * 100) : null)
const orNull = (s) => (s === '' || s == null ? null : s)

function readJsonl(path) {
  if (existsSync(path)) return readFileSync(path, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l))
  if (existsSync(`${path}.gz`)) return gunzipSync(readFileSync(`${path}.gz`)).toString('utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l))
  return []
}

/** Units per EUR on or before a date, for a currency. */
async function loadFx(mastersDir) {
  const byCurrency = new Map()
  await eachCsv(join(mastersDir, 'fx_rates.csv'), (r) => {
    const list = byCurrency.get(r.currency) ?? []
    list.push([r.date, Number(r.units_per_eur)])
    byCurrency.set(r.currency, list)
  })
  return (centsAmount, currency, date) => {
    if (currency === 'EUR') return centsAmount
    const list = byCurrency.get(currency)
    if (!list) return centsAmount
    let lo = 0
    let hi = list.length - 1
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1
      if (list[mid][0] <= date) lo = mid
      else hi = mid - 1
    }
    return Math.round(centsAmount / list[lo][1])
  }
}

export async function loadRealRun(runDir, dbDir) {
  const started = Date.now()
  const log = (what) => console.log(`${((Date.now() - started) / 1000).toFixed(1)} s · ${what}`)
  const run = JSON.parse(readFileSync(join(runDir, 'run.json'), 'utf8'))
  const phaseDir = join(dbDir, run.phase)
  const finalMasters = join(phaseDir, 'masters_final')
  const mastersDir = existsSync(finalMasters) ? finalMasters : join(dbDir, 'bankrec-docs-and-masters', 'masters')
  const toEur = await loadFx(mastersDir)

  const entities = []
  await eachCsv(join(mastersDir, 'entities.csv'), (r) => entities.push({ entity: r.entity, name: r.legal_name }))
  const parties = []
  await eachCsv(join(mastersDir, 'customers.csv'), (r) =>
    parties.push({ partyId: r.customer_id, kind: 'customer', entity: r.entity, name: r.name, tradeName: orNull(r.trade_name), type: orNull(r.customer_type), country: orNull(r.country), taxId: orNull(r.tax_id), iban: orNull(r.iban), paymentTerms: orNull(r.payment_terms), currency: orNull(r.invoice_currency), groupId: orNull(r.group_id), parentId: orNull(r.parent_customer_id), blockedSince: orNull(r.blocked_since) }),
  )
  await eachCsv(join(mastersDir, 'suppliers.csv'), (r) =>
    parties.push({ partyId: r.supplier_id, kind: 'supplier', entity: r.entity, name: r.name, tradeName: null, type: orNull(r.supplier_type), country: orNull(r.country), taxId: orNull(r.tax_id), iban: orNull(r.iban), paymentTerms: orNull(r.payment_terms), currency: orNull(r.invoice_currency), groupId: null, parentId: null, blockedSince: orNull(r.blocked_since) }),
  )
  const partyById = new Map(parties.map((p) => [p.partyId, p]))
  log(`${parties.length} terceros`)

  const items = []
  const push = (itemType, r, documentNumber, partyId, partyName, extra = {}) =>
    items.push({ itemId: r.item_id, itemType, entity: r.entity, documentNumber, partyId, partyName, issueDate: r.issue_date, dueDate: orNull(r.due_date), currency: r.currency, totalCents: cents(r.total_amount), openAtStartCents: null, relatedDocument: null, reference: null, ...extra })
  await eachCsv(join(phaseDir, 'ar_invoices.csv.gz'), (r) => push('ARI', r, r.document_number, r.customer_id, r.customer_name, { reference: orNull(r.customer_po) }))
  await eachCsv(join(phaseDir, 'ap_invoices.csv.gz'), (r) => push('API', r, r.supplier_invoice_number, r.supplier_id, r.supplier_name, { reference: orNull(r.our_po) }))
  await eachCsv(join(phaseDir, 'credit_notes.csv.gz'), (r) => push(r.item_id.slice(0, 3), r, r.document_number, r.party_id, r.party_name, { relatedDocument: orNull(r.related_document) }))
  const itemById = new Map(items.map((i) => [i.itemId, i]))
  await eachCsv(join(phaseDir, 'open_items_at_start.csv.gz'), (r) => {
    const known = itemById.get(r.item_id)
    if (known) {
      known.openAtStartCents = cents(r.open_amount)
      return
    }
    const item = { itemId: r.item_id, itemType: r.item_type, entity: r.entity, documentNumber: r.document_number, partyId: r.party_id, partyName: partyById.get(r.party_id)?.name ?? r.party_id, issueDate: r.issue_date, dueDate: orNull(r.due_date), currency: r.currency, totalCents: cents(r.total_amount), openAtStartCents: cents(r.open_amount), relatedDocument: null, reference: null }
    items.push(item)
    itemById.set(item.itemId, item)
  })
  log(`${items.length} partidas`)

  const explanations = readJsonl(join(runDir, 'explanations.jsonl'))
  const explainedTxns = new Set()
  for (const e of explanations) {
    e.documentNumber = e.itemId ? itemById.get(e.itemId)?.documentNumber ?? null : null
    if (e.itemId) explainedTxns.add(e.bankTxnId)
  }
  log(`${explanations.length} filas`)

  const txns = []
  const accountsSeen = new Map()
  await eachCsv(join(phaseDir, 'bank_transactions.csv.gz'), (r) => {
    const amountCents = cents(r.amount)
    txns.push({
      bankTxnId: r.bank_txn_id, accountId: r.account_id, entity: r.entity, bank: r.bank, statementFormat: r.statement_format, statementFile: r.statement_file, bookingDate: r.booking_date, valueDate: r.value_date, amountCents, currency: r.currency,
      bankCode: orNull(r.bank_code), bankSubcode: orNull(r.bank_subcode), ref1: orNull(r.ref1), ref2: orNull(r.ref2), text: r.text, counterpartyName: orNull(r.counterparty_name), counterpartyAccount: orNull(r.counterparty_account), endToEndId: orNull(r.end_to_end_id), remittanceInfo: orNull(r.remittance_info), origAmountCents: cents(r.orig_amount), origCurrency: orNull(r.orig_currency),
      amountEur: toEur(amountCents, r.currency, r.booking_date), identified: explainedTxns.has(r.bank_txn_id),
    })
    if (!accountsSeen.has(r.account_id)) accountsSeen.set(r.account_id, r)
  })
  log(`${txns.length} movimientos`)

  const accounts = []
  await eachCsv(join(mastersDir, 'bank_accounts.csv'), (r) => {
    const format = r.statement_format
    const next = r.statement_format_from_2025_10_01
    accounts.push({ accountId: r.account_id, entity: r.entity, bank: r.bank, bankName: orNull(r.bank_name), currency: r.currency, iban: orNull(r.iban), purpose: orNull(r.purpose), inMaster: true, formats: next && next !== format ? [{ format, from: '2025-07-01', to: '2025-09-30' }, { format: next, from: '2025-10-01', to: null }] : [{ format, from: '2025-07-01', to: null }] })
  })
  for (const [accountId, r] of accountsSeen) {
    if (!accounts.some((a) => a.accountId === accountId)) accounts.push({ accountId, entity: r.entity, bank: r.bank, bankName: null, currency: r.currency, iban: null, purpose: null, inMaster: false, formats: [{ format: r.statement_format, from: '2025-07-01', to: null }] })
  }

  // Open items, recomputed: what the rows applied against the opening balance or the document total.
  const applied = new Map()
  const txnById = new Map(txns.map((t) => [t.bankTxnId, t]))
  for (const e of explanations) {
    if (!e.itemId) continue
    const list = applied.get(e.itemId) ?? []
    list.push({ bankTxnId: e.bankTxnId, bookingDate: txnById.get(e.bankTxnId)?.bookingDate ?? null, amountCents: e.amountCents, exception: e.exception })
    applied.set(e.itemId, list)
  }
  const asOf = txns.reduce((max, t) => (t.bookingDate > max ? t.bookingDate : max), '')
  const asOfMs = Date.parse(asOf)
  const openItems = items.map((i) => {
    const history = applied.get(i.itemId) ?? []
    const start = i.openAtStartCents ?? i.totalCents
    const paid = history.reduce((sum, h) => sum + (h.exception === 'RETURNED' ? -h.amountCents : h.amountCents), 0)
    const open = Math.max(0, start - paid)
    const daysOverdue = open > 0 && i.dueDate && i.dueDate < asOf ? Math.round((asOfMs - Date.parse(i.dueDate)) / 86400000) : 0
    return {
      itemId: i.itemId, itemType: i.itemType, entity: i.entity, partyId: i.partyId, partyName: i.partyName, documentNumber: i.documentNumber, issueDate: i.issueDate, dueDate: i.dueDate, currency: i.currency, totalCents: i.totalCents,
      openAtStartCents: i.openAtStartCents ?? 0, appliedCents: paid, openAtEndCents: open, openAtEndEur: toEur(open, i.currency, asOf),
      status: open === 0 ? 'cleared' : history.some((h) => h.exception === 'SHORT_DISPUTE') ? 'disputed' : open < start ? 'partial' : 'open', daysOverdue, history,
    }
  })
  log(`${openItems.length} partidas con saldo`)

  const partyFacts = []
  const seenFact = new Set()
  for (const e of explanations) {
    if (!e.partyId || seenFact.has(e.bankTxnId)) continue
    seenFact.add(e.bankTxnId)
    partyFacts.push({ bankTxnId: e.bankTxnId, partyId: e.partyId, partyKind: partyById.get(e.partyId)?.kind ?? 'customer', payerName: txnById.get(e.bankTxnId)?.counterpartyName ?? null, how: 'file', confidence: e.confidence, alternatives: [] })
  }

  const documents = []
  await eachCsv(join(phaseDir, 'remittance_advices', 'index.csv'), (r) =>
    documents.push({ path: `remittance_advices/${r.file}`, kind: 'remittanceAdvice', entity: r.entity, format: r.format, name: r.file.split('/').pop(), date: orNull(r.received_date), partyName: orNull(r.payer_name) }),
  )
  const PDF_KIND = { invoice: 'invoicePdf', supplier_invoice: 'invoicePdf', credit_note: 'creditNotePdf', supplier_credit_note: 'creditNotePdf', proforma: 'proformaPdf', bank_account_notice: 'bankAccountNotice' }
  await eachCsv(join(phaseDir, 'pdfs', 'index.csv'), (r) =>
    documents.push({ path: `pdfs/${r.file}`, kind: PDF_KIND[r.document_type] ?? 'bankAccountNotice', entity: r.entity, format: 'pdf', name: r.file.split('/').pop(), date: orNull(r.document_date), partyName: partyById.get(r.party_id)?.name ?? null }),
  )

  const detailFiles = []
  for (const [dir, kind] of [['direct_debit_batches', 'directDebitBatch'], ['card_settlements', 'cardSettlement'], ['cheque_deposits', 'chequeDeposit'], ['payment_runs', 'paymentRun']]) {
    if (!existsSync(join(phaseDir, dir))) continue
    for (const file of readdirSync(join(phaseDir, dir))) {
      if (!file.endsWith('.csv')) continue
      const month = /_(\d{4})(\d{2})/.exec(file)
      detailFiles.push({ path: `${dir}/${file}`, kind, entity: file.slice(0, 4), month: month ? `${month[1]}-${month[2]}` : null, rows: Math.round(statSync(join(phaseDir, dir, file)).size / 150) })
    }
  }
  log(`${documents.length} documentos, ${detailFiles.length} ficheros de detalle`)

  return {
    run, phaseDir, asOf,
    masters: { entities, accounts },
    txns, explanations, items, openItems, parties, partyFacts, documents, detailFiles, documentFacts: [],
    // CONTRACT.md §2.2: a case's amount is a magnitude; the sign is in the movement.
    cases: readJsonl(join(runDir, 'cases.jsonl')).map((c) => ({ ...c, amountCents: Math.abs(c.amountCents), amountEur: Math.abs(c.amountEur) })), questions: readJsonl(join(runDir, 'questions.jsonl')), drafts: readJsonl(join(runDir, 'drafts.jsonl')),
    /** Text of a document on disk: PDFs and xlsx have none without the extraction facts. */
    documentText(path) {
      if (/\.(pdf|xlsx)$/.test(path)) return null
      const file = join(phaseDir, path)
      return existsSync(file) ? readFileSync(file, 'latin1') : null
    },
    /** The rows of a detail file that mention one of the movement's documents. */
    detailRows(path, documentNumbers, limit = 500) {
      const file = join(phaseDir, path)
      if (!existsSync(file)) return null
      const [head, ...lines] = readFileSync(file, 'utf8').split('\n')
      const wanted = documentNumbers.filter(Boolean)
      const rows = lines.filter((l) => wanted.some((d) => l.includes(d))).slice(0, limit).map(splitCsv)
      return { columns: splitCsv(head), rows }
    },
  }
}
