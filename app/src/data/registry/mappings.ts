// Which package files feed each kind and how their rows become domain objects.
// This is the file to edit when the real package arrives (ARCHITECTURE.md §4.2): `files` and `map` only.
// Pure (no React): it also runs inside the import worker.
import type { BankTransaction, Contract, DatasetKind, Entity, ErpEvent, Invoice, LedgerEntry, ObjectKind, PurchaseOrder, Vendor } from '@/domain'
import { decimalToCents } from '../parsers/text'
import type { RawRow } from '../parsers/tabular'

export interface Mapping<T> {
  kind: DatasetKind
  /** True when a package file (path inside the zip) holds rows of this kind. */
  files: (path: string) => boolean
  /** One raw row → one domain object. Throws with a Spanish message when a required field is missing. */
  map: (row: RawRow) => T
}

/** `facturas.csv`, `data/invoices_2026-09.jsonl`… : base name starts with one of the names, any tabular extension. */
const named =
  (...names: string[]) =>
  (path: string) => {
    const base = path.split('/').pop()!.toLowerCase()
    return /\.(csv|jsonl|ndjson|json)$/.test(base) && names.some((n) => base.startsWith(n))
  }

/** First non-empty value among the aliases of a field. */
function pick(row: RawRow, keys: string[]): unknown {
  for (const k of keys) {
    const v = row[k]
    if (v !== undefined && v !== null && v !== '') return v
  }
  return undefined
}

function str(row: RawRow, ...keys: string[]): string {
  const v = pick(row, keys)
  if (v === undefined) throw new Error(`Falta el campo ${keys[0]}`)
  return String(v).trim()
}

function strOr(row: RawRow, ...keys: string[]): string | null {
  const v = pick(row, keys)
  return v === undefined ? null : String(v).trim()
}

function numOr(row: RawRow, ...keys: string[]): number | null {
  const v = pick(row, keys)
  if (v === undefined) return null
  const n = typeof v === 'number' ? v : Number(String(v).replace(',', '.'))
  return Number.isFinite(n) ? n : null
}

/** Money field: `fooCents` (integer cents) or `foo` (decimal amount, any separator). */
function cents(row: RawRow, name: string, ...aliases: string[]): number {
  const c = pick(row, [`${name}Cents`, `${name}_cents`])
  if (c !== undefined) {
    const n = Number(c)
    if (Number.isInteger(n)) return n
  }
  const v = pick(row, [name, ...aliases])
  if (v === undefined) throw new Error(`Falta el importe ${name}`)
  const n = typeof v === 'number' ? Math.round(v * 100) : decimalToCents(String(v))
  if (Number.isNaN(n)) throw new Error(`Importe ${name} no numérico: ${String(v)}`)
  return n
}

function centsOr(row: RawRow, name: string, ...aliases: string[]): number | null {
  try {
    return cents(row, name, ...aliases)
  } catch {
    return null
  }
}

const ENTITY = ['entityId', 'entity_id', 'company', 'sociedad']
const CURRENCY = ['currency', 'moneda']

const entities: Mapping<Entity> = {
  kind: 'entities',
  files: named('entities', 'companies', 'sociedades', 'empresas'),
  map: (r) => ({
    id: str(r, 'id', 'entityId', 'company_id'),
    name: str(r, 'name', 'nombre'),
    country: str(r, 'country', 'pais'),
    currency: str(r, ...CURRENCY),
    taxId: strOr(r, 'taxId', 'tax_id', 'nif', 'cif'),
    parentId: strOr(r, 'parentId', 'parent_id'),
  }),
}

const vendors: Mapping<Vendor> = {
  kind: 'vendors',
  files: named('vendors', 'suppliers', 'proveedores'),
  map: (r) => ({
    id: str(r, 'id', 'vendorId', 'vendor_id'),
    entityId: str(r, ...ENTITY),
    name: str(r, 'name', 'nombre'),
    taxId: strOr(r, 'taxId', 'tax_id', 'nif', 'cif'),
    iban: strOr(r, 'iban', 'bankAccount', 'bank_account'),
    country: strOr(r, 'country', 'pais'),
    paymentTermsDays: numOr(r, 'paymentTermsDays', 'payment_terms_days'),
  }),
}

const contracts: Mapping<Contract> = {
  kind: 'contracts',
  files: named('contracts', 'contratos'),
  map: (r) => ({
    id: str(r, 'id', 'contractId', 'contract_id'),
    entityId: str(r, ...ENTITY),
    vendorId: strOr(r, 'vendorId', 'vendor_id', 'counterpartyId'),
    title: str(r, 'title', 'description', 'descripcion'),
    startDate: str(r, 'startDate', 'start_date'),
    endDate: strOr(r, 'endDate', 'end_date'),
    amountCents: centsOr(r, 'amount', 'value'),
    currency: str(r, ...CURRENCY),
  }),
}

const purchaseOrders: Mapping<PurchaseOrder> = {
  kind: 'purchaseOrders',
  files: named('purchase_orders', 'purchaseorders', 'pos', 'ordenes', 'pedidos'),
  map: (r) => ({
    id: str(r, 'id', 'poId', 'po_id', 'purchaseOrderId'),
    entityId: str(r, ...ENTITY),
    vendorId: str(r, 'vendorId', 'vendor_id'),
    contractId: strOr(r, 'contractId', 'contract_id'),
    date: str(r, 'date', 'orderDate', 'order_date'),
    status: strOr(r, 'status', 'estado') ?? 'open',
    amountCents: cents(r, 'amount', 'total'),
    currency: str(r, ...CURRENCY),
  }),
}

const invoices: Mapping<Invoice> = {
  kind: 'invoices',
  files: named('invoices', 'facturas', 'ap_invoices'),
  map: (r) => ({
    id: str(r, 'id', 'invoiceId', 'invoice_id'),
    entityId: str(r, ...ENTITY),
    vendorId: str(r, 'vendorId', 'vendor_id'),
    number: str(r, 'number', 'invoiceNumber', 'invoice_number', 'numero'),
    purchaseOrderId: strOr(r, 'purchaseOrderId', 'po_id', 'poId'),
    issueDate: str(r, 'issueDate', 'issue_date', 'date', 'fecha'),
    dueDate: strOr(r, 'dueDate', 'due_date'),
    netCents: cents(r, 'net', 'base'),
    taxCents: cents(r, 'tax', 'vat', 'iva'),
    taxRate: numOr(r, 'taxRate', 'tax_rate', 'vatRate'),
    totalCents: cents(r, 'total', 'gross'),
    currency: str(r, ...CURRENCY),
    iban: strOr(r, 'iban', 'bankAccount', 'bank_account'),
    status: strOr(r, 'status', 'estado') ?? 'pending',
  }),
}

const bankTransactions: Mapping<BankTransaction> = {
  kind: 'bankTransactions',
  files: named('bank_transactions', 'bank_statement', 'transactions', 'movimientos', 'extracto'),
  map: (r) => ({
    id: str(r, 'id', 'transactionId', 'transaction_id'),
    entityId: str(r, ...ENTITY),
    accountIban: str(r, 'accountIban', 'account_iban', 'account', 'cuenta'),
    date: str(r, 'date', 'bookingDate', 'booking_date', 'fecha'),
    description: str(r, 'description', 'concept', 'concepto'),
    counterparty: strOr(r, 'counterparty', 'contraparte'),
    counterpartyIban: strOr(r, 'counterpartyIban', 'counterparty_iban'),
    amountCents: cents(r, 'amount', 'importe'),
    currency: str(r, ...CURRENCY),
  }),
}

const ledgerEntries: Mapping<LedgerEntry> = {
  kind: 'ledgerEntries',
  files: named('ledger', 'general_ledger', 'journal', 'libro_mayor', 'diario'),
  map: (r) => ({
    id: str(r, 'id', 'lineId', 'line_id'),
    entityId: str(r, ...ENTITY),
    entryId: str(r, 'entryId', 'entry_id', 'asiento'),
    date: str(r, 'date', 'postingDate', 'posting_date', 'fecha'),
    account: str(r, 'account', 'cuenta'),
    accountName: strOr(r, 'accountName', 'account_name'),
    description: strOr(r, 'description', 'concepto') ?? '',
    debitCents: centsOr(r, 'debit', 'debe') ?? 0,
    creditCents: centsOr(r, 'credit', 'haber') ?? 0,
    currency: str(r, ...CURRENCY),
    sourceRef: strOr(r, 'sourceRef', 'source_ref', 'documentId'),
  }),
}

const OBJECT_KINDS: ObjectKind[] = ['entity', 'vendor', 'contract', 'purchaseOrder', 'invoice', 'bankTransaction', 'ledgerEntry', 'erpEvent']

const erpEvents: Mapping<ErpEvent> = {
  kind: 'erpEvents',
  files: named('erp_history', 'erp_events', 'audit_log', 'change_log', 'historial'),
  map: (r) => {
    const kind = str(r, 'subjectKind', 'object_type', 'objectType')
    if (!OBJECT_KINDS.includes(kind as ObjectKind)) throw new Error(`Tipo de objeto desconocido: ${kind}`)
    return {
      id: str(r, 'id', 'eventId', 'event_id'),
      entityId: str(r, ...ENTITY),
      at: str(r, 'at', 'timestamp', 'changed_at'),
      user: strOr(r, 'user', 'changed_by'),
      action: str(r, 'action', 'accion'),
      subject: { kind: kind as ObjectKind, id: str(r, 'subjectId', 'object_id', 'objectId') },
      field: strOr(r, 'field', 'campo'),
      before: strOr(r, 'before', 'old_value'),
      after: strOr(r, 'after', 'new_value'),
    }
  },
}

/** In Dataset order. A file is read by the first mapping whose `files` accepts it. */
export const MAPPINGS = [entities, vendors, contracts, purchaseOrders, invoices, bankTransactions, ledgerEntries, erpEvents] as const
