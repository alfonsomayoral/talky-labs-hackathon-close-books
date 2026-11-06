// Client inputs, normalized. Shapes are provisional until the official package arrives (PROBLEM.md §4):
// only `files` and `map` in data/registry change then, these types should not.

/** Integer cents plus ISO 4217 currency. Never sum different currencies. */
export interface Money {
  amountCents: number
  currency: string
}

export interface Entity {
  id: string
  name: string
  country: string
  currency: string
  taxId: string | null
  /** Parent entity in the group, null for the holding. */
  parentId: string | null
}

export interface Vendor {
  id: string
  entityId: string
  name: string
  taxId: string | null
  iban: string | null
  country: string | null
  paymentTermsDays: number | null
}

export interface Contract {
  id: string
  entityId: string
  vendorId: string | null
  title: string
  startDate: string
  endDate: string | null
  amountCents: number | null
  currency: string
}

export interface PurchaseOrder {
  id: string
  entityId: string
  vendorId: string
  contractId: string | null
  date: string
  status: string
  amountCents: number
  currency: string
}

export interface Invoice {
  id: string
  entityId: string
  vendorId: string
  number: string
  purchaseOrderId: string | null
  issueDate: string
  dueDate: string | null
  netCents: number
  taxCents: number
  /** Tax rate as a ratio (0.21), as stated on the invoice. */
  taxRate: number | null
  totalCents: number
  currency: string
  /** IBAN printed on the invoice; may differ from the vendor master. */
  iban: string | null
  status: string
}

export interface BankTransaction {
  id: string
  entityId: string
  accountIban: string
  date: string
  description: string
  counterparty: string | null
  counterpartyIban: string | null
  /** Positive = money in, negative = money out. */
  amountCents: number
  currency: string
}

export interface LedgerEntry {
  id: string
  entityId: string
  entryId: string
  date: string
  account: string
  accountName: string | null
  description: string
  debitCents: number
  creditCents: number
  currency: string
  /** Source document id when the ERP links one (invoice, payment…). */
  sourceRef: string | null
}

/** One change recorded by the ERP on any object (e.g. a vendor's IBAN). */
export interface ErpEvent {
  id: string
  entityId: string
  at: string
  user: string | null
  action: string
  subject: ObjectRef
  field: string | null
  before: string | null
  after: string | null
}

export type ObjectKind = 'entity' | 'vendor' | 'contract' | 'purchaseOrder' | 'invoice' | 'bankTransaction' | 'ledgerEntry' | 'erpEvent'

export interface ObjectRef {
  kind: ObjectKind
  id: string
}

/** A file of the package that no registry spec reads: kept and shown raw. */
export interface RawFile {
  path: string
  size: number
  /** First rows when the file is tabular (CSV, JSON, JSONL), for the raw viewer. */
  preview: Record<string, unknown>[] | null
}

/** A row a spec could not map. The load continues without it. */
export interface DataIssue {
  path: string
  row: number
  message: string
}

export interface DatasetMeta {
  name: string
  /** `YYYY-MM` of the close, or null while unknown. */
  period: string | null
  source: 'fixtures' | 'zip'
  loadedAt: string
}

export interface Dataset {
  meta: DatasetMeta
  entities: Entity[]
  vendors: Vendor[]
  contracts: Contract[]
  purchaseOrders: PurchaseOrder[]
  invoices: Invoice[]
  bankTransactions: BankTransaction[]
  ledgerEntries: LedgerEntry[]
  erpEvents: ErpEvent[]
  unmapped: RawFile[]
  issues: DataIssue[]
}

/** Keys of Dataset that hold objects of a kind, in sidebar order. */
export type DatasetKind = 'entities' | 'vendors' | 'contracts' | 'purchaseOrders' | 'invoices' | 'bankTransactions' | 'ledgerEntries' | 'erpEvents'

export const KIND_OF: Record<DatasetKind, ObjectKind> = {
  entities: 'entity',
  vendors: 'vendor',
  contracts: 'contract',
  purchaseOrders: 'purchaseOrder',
  invoices: 'invoice',
  bankTransactions: 'bankTransaction',
  ledgerEntries: 'ledgerEntry',
  erpEvents: 'erpEvent',
}
