// How each kind is shown: sidebar entry, table columns, search text, facet and panel details.
// Works on domain types only, so it does not change when the package format does (that is mappings.ts).
import type { ReactNode } from 'react'
import { BookOpen, Building2, FileSignature, FileText, History, Landmark, ShoppingCart, Truck, type LucideIcon } from 'lucide-react'
import { Amount, Badge, Mono, type Column, type KeyValueItem } from '@/components'
import type { BankTransaction, Contract, DatasetKind, Entity, ErpEvent, Invoice, LedgerEntry, ObjectKind, ObjectRef, PurchaseOrder, Vendor } from '@/domain'
import { KIND_OF } from '@/domain'
import { formatDate, formatDateTime, formatPercent } from '@/lib/format'
import type { AnyObject, Links } from '../links'
import { MATCH_STATUS } from './vocabulary'

export interface Facet<T> {
  label: string
  value: (o: T, links: Links) => string
}

export interface DatasetView<T extends AnyObject = AnyObject> {
  kind: DatasetKind
  label: string
  /** Sidebar label when `label` is too long for it. */
  navLabel?: string
  /** Route of its page; null when the kind is only shown inside other objects' panels. */
  path: string | null
  icon: LucideIcon
  /** What the package holds of this kind, in one sentence. */
  description: string
  /** One line naming the object (panel title, related lists, cards). */
  title: (o: T, links: Links) => string
  /** The object's key figure or date, shown right of its title in cards and related lists. */
  aside: (o: T) => ReactNode
  columns: (links: Links) => Column<T>[]
  search: (o: T, links: Links) => string
  facet?: Facet<T>
  detail: (o: T, links: Links) => KeyValueItem[]
}

const name = (links: Links, ref: ObjectRef): string => {
  const o = links.get(ref) as { name?: string } | undefined
  return o?.name ?? ref.id
}

const entityCol = <T extends { entityId: string }>(): Column<T> => ({
  id: 'entity',
  header: 'Sociedad',
  width: 92,
  cell: (o) => <Mono muted>{o.entityId}</Mono>,
  sortValue: (o) => o.entityId,
})

const idCol = <T extends AnyObject>(header: string, width = 150): Column<T> => ({
  id: 'id',
  header,
  width,
  cell: (o) => <Mono>{o.id}</Mono>,
  sortValue: (o) => o.id,
})

/** ERP actions in Spanish; unknown actions show as they come. */
const ERP_ACTION: Record<string, string> = { create: 'Alta', update: 'Cambio', delete: 'Baja' }

export const erpActionLabel = (action: string) => ERP_ACTION[action] ?? action

const money = (cents: number | null, currency: string): ReactNode => <Amount cents={cents} currency={currency} />

const define = <T extends AnyObject>(v: DatasetView<T>) => v as unknown as DatasetView

export const VIEWS: DatasetView[] = [
  define<Entity>({
    kind: 'entities',
    description: 'Las sociedades del grupo, con su país, su moneda y su dominante.',
    aside: (e) => e.currency,
    label: 'Sociedades',
    path: '/sociedades',
    icon: Building2,
    title: (e) => e.name,
    columns: () => [
      idCol('Código', 90),
      { id: 'name', header: 'Nombre', width: 'minmax(220px, 2fr)', cell: (e) => e.name, sortValue: (e) => e.name },
      { id: 'country', header: 'País', width: 70, cell: (e) => e.country, sortValue: (e) => e.country },
      { id: 'currency', header: 'Moneda', width: 80, cell: (e) => <Mono>{e.currency}</Mono> },
      { id: 'taxId', header: 'NIF', width: 140, cell: (e) => <Mono muted>{e.taxId ?? '—'}</Mono> },
      { id: 'parent', header: 'Dominante', width: 110, cell: (e) => (e.parentId ? <Mono muted>{e.parentId}</Mono> : <Badge tone="brand">Holding</Badge>) },
    ],
    search: (e) => `${e.id} ${e.name} ${e.taxId ?? ''}`,
    facet: { label: 'País', value: (e) => e.country },
    detail: (e, links) => [
      { label: 'Código', value: e.id, mono: true },
      { label: 'País', value: e.country },
      { label: 'Moneda', value: e.currency, mono: true },
      { label: 'NIF', value: e.taxId ?? '—', mono: true },
      { label: 'Dominante', value: e.parentId ? name(links, { kind: 'entity', id: e.parentId }) : 'Es la cabecera del grupo' },
    ],
  }),
  define<Vendor>({
    kind: 'vendors',
    description: 'La ficha de cada proveedor: NIF, IBAN y plazo de pago.',
    aside: (v) => <Mono muted>{v.iban ? `${v.iban.slice(0, 2)} ···· ${v.iban.slice(-4)}` : 'Sin IBAN'}</Mono>,
    label: 'Proveedores',
    path: '/proveedores',
    icon: Truck,
    title: (v) => v.name,
    columns: () => [
      idCol('Proveedor', 100),
      entityCol(),
      { id: 'name', header: 'Nombre', width: 'minmax(220px, 2fr)', cell: (v) => v.name, sortValue: (v) => v.name },
      { id: 'taxId', header: 'NIF', width: 130, cell: (v) => <Mono muted>{v.taxId ?? '—'}</Mono> },
      { id: 'iban', header: 'IBAN', width: 'minmax(220px, 1fr)', cell: (v) => <Mono muted>{v.iban ?? '—'}</Mono> },
      { id: 'terms', header: 'Plazo', width: 70, align: 'right', cell: (v) => (v.paymentTermsDays == null ? '—' : `${v.paymentTermsDays} d`), sortValue: (v) => v.paymentTermsDays },
    ],
    search: (v) => `${v.id} ${v.name} ${v.taxId ?? ''} ${v.iban ?? ''}`,
    facet: { label: 'País', value: (v) => v.country ?? '—' },
    detail: (v, links) => [
      { label: 'Proveedor', value: v.id, mono: true },
      { label: 'Sociedad', value: name(links, { kind: 'entity', id: v.entityId }) },
      { label: 'NIF', value: v.taxId ?? '—', mono: true },
      { label: 'IBAN en la ficha', value: v.iban ?? '—', mono: true },
      { label: 'País', value: v.country ?? '—' },
      { label: 'Plazo de pago', value: v.paymentTermsDays == null ? '—' : `${v.paymentTermsDays} días` },
    ],
  }),
  define<Contract>({
    kind: 'contracts',
    description: 'Contratos con proveedores: objeto, vigencia e importe pactado.',
    aside: (c) => money(c.amountCents, c.currency),
    label: 'Contratos',
    path: '/contratos',
    icon: FileSignature,
    title: (c) => c.title,
    columns: (links) => [
      idCol('Contrato', 130),
      entityCol(),
      { id: 'title', header: 'Objeto', width: 'minmax(200px, 2fr)', cell: (c) => c.title, sortValue: (c) => c.title },
      { id: 'vendor', header: 'Contraparte', width: 'minmax(180px, 1.5fr)', cell: (c) => (c.vendorId ? name(links, { kind: 'vendor', id: c.vendorId }) : '—') },
      { id: 'period', header: 'Vigencia', width: 200, cell: (c) => `${formatDate(c.startDate)} – ${c.endDate ? formatDate(c.endDate) : 'indefinida'}`, sortValue: (c) => c.startDate },
      { id: 'amount', header: 'Importe', width: 140, align: 'right', cell: (c) => money(c.amountCents, c.currency), sortValue: (c) => c.amountCents },
    ],
    search: (c, links) => `${c.id} ${c.title} ${c.vendorId ? name(links, { kind: 'vendor', id: c.vendorId }) : ''}`,
    detail: (c, links) => [
      { label: 'Contrato', value: c.id, mono: true },
      { label: 'Sociedad', value: name(links, { kind: 'entity', id: c.entityId }) },
      { label: 'Contraparte', value: c.vendorId ? name(links, { kind: 'vendor', id: c.vendorId }) : '—' },
      { label: 'Vigencia', value: `${formatDate(c.startDate)} – ${c.endDate ? formatDate(c.endDate) : 'indefinida'}` },
      { label: 'Importe', value: money(c.amountCents, c.currency) },
    ],
  }),
  define<PurchaseOrder>({
    kind: 'purchaseOrders',
    description: 'Pedidos emitidos a proveedores, con su contrato y su importe.',
    aside: (p) => money(p.amountCents, p.currency),
    label: 'Órdenes de compra',
    navLabel: 'Pedidos',
    path: '/pedidos',
    icon: ShoppingCart,
    title: (p, links) => `${p.id} · ${name(links, { kind: 'vendor', id: p.vendorId })}`,
    columns: (links) => [
      idCol('Pedido', 140),
      entityCol(),
      { id: 'date', header: 'Fecha', width: 110, cell: (p) => formatDate(p.date), sortValue: (p) => p.date },
      { id: 'vendor', header: 'Proveedor', width: 'minmax(200px, 2fr)', cell: (p) => name(links, { kind: 'vendor', id: p.vendorId }) },
      { id: 'contract', header: 'Contrato', width: 140, cell: (p) => <Mono muted>{p.contractId ?? '—'}</Mono> },
      { id: 'status', header: 'Estado', width: 100, cell: (p) => p.status },
      { id: 'amount', header: 'Importe', width: 140, align: 'right', cell: (p) => money(p.amountCents, p.currency), sortValue: (p) => p.amountCents },
    ],
    search: (p, links) => `${p.id} ${name(links, { kind: 'vendor', id: p.vendorId })} ${p.contractId ?? ''}`,
    facet: { label: 'Estado', value: (p) => p.status },
    detail: (p, links) => [
      { label: 'Pedido', value: p.id, mono: true },
      { label: 'Sociedad', value: name(links, { kind: 'entity', id: p.entityId }) },
      { label: 'Proveedor', value: name(links, { kind: 'vendor', id: p.vendorId }) },
      { label: 'Contrato', value: p.contractId ?? '—', mono: true },
      { label: 'Fecha', value: formatDate(p.date) },
      { label: 'Estado', value: p.status },
      { label: 'Importe', value: money(p.amountCents, p.currency) },
    ],
  }),
  define<Invoice>({
    kind: 'invoices',
    description: 'Facturas recibidas: base, impuesto, total, pedido e IBAN de cobro.',
    aside: (i) => money(i.totalCents, i.currency),
    label: 'Facturas',
    path: '/facturas',
    icon: FileText,
    title: (i, links) => `${i.number} · ${name(links, { kind: 'vendor', id: i.vendorId })}`,
    columns: (links) => [
      { id: 'number', header: 'Número', width: 128, cell: (i) => <Mono>{i.number}</Mono>, sortValue: (i) => i.number },
      entityCol(),
      { id: 'date', header: 'Emisión', width: 110, cell: (i) => formatDate(i.issueDate), sortValue: (i) => i.issueDate },
      { id: 'vendor', header: 'Proveedor', width: 'minmax(200px, 2fr)', cell: (i) => name(links, { kind: 'vendor', id: i.vendorId }) },
      { id: 'po', header: 'Pedido', width: 128, cell: (i) => <Mono muted>{i.purchaseOrderId ?? '—'}</Mono> },
      { id: 'net', header: 'Base', width: 116, align: 'right', cell: (i) => money(i.netCents, i.currency), sortValue: (i) => i.netCents },
      { id: 'tax', header: 'Impuesto', width: 104, align: 'right', cell: (i) => money(i.taxCents, i.currency), sortValue: (i) => i.taxCents },
      { id: 'total', header: 'Total', width: 124, align: 'right', cell: (i) => money(i.totalCents, i.currency), sortValue: (i) => i.totalCents },
    ],
    search: (i, links) => `${i.id} ${i.number} ${name(links, { kind: 'vendor', id: i.vendorId })} ${i.purchaseOrderId ?? ''}`,
    facet: { label: 'Estado', value: (i) => i.status },
    detail: (i, links) => [
      { label: 'Número', value: i.number, mono: true },
      { label: 'Id interno', value: i.id, mono: true },
      { label: 'Sociedad', value: name(links, { kind: 'entity', id: i.entityId }) },
      { label: 'Proveedor', value: name(links, { kind: 'vendor', id: i.vendorId }) },
      { label: 'Pedido', value: i.purchaseOrderId ?? 'Sin pedido', mono: true },
      { label: 'Emisión · vencimiento', value: `${formatDate(i.issueDate)} · ${i.dueDate ? formatDate(i.dueDate) : '—'}` },
      { label: 'Base', value: money(i.netCents, i.currency) },
      { label: `Impuesto${i.taxRate == null ? '' : ` (${formatPercent(i.taxRate)})`}`, value: money(i.taxCents, i.currency) },
      { label: 'Total', value: money(i.totalCents, i.currency) },
      { label: 'IBAN en la factura', value: i.iban ?? '—', mono: true },
      { label: 'Estado', value: i.status },
    ],
  }),
  define<BankTransaction>({
    kind: 'bankTransactions',
    description: 'Movimientos del extracto de cada cuenta, con su conciliación.',
    aside: (t) => <Amount cents={t.amountCents} currency={t.currency} colorize />,
    label: 'Transacciones bancarias',
    navLabel: 'Banco',
    path: '/banco',
    icon: Landmark,
    title: (t) => t.description,
    columns: (links) => [
      { id: 'date', header: 'Fecha', width: 110, cell: (t) => formatDate(t.date), sortValue: (t) => t.date },
      entityCol(),
      { id: 'description', header: 'Concepto', width: 'minmax(260px, 3fr)', cell: (t) => t.description, sortValue: (t) => t.description },
      { id: 'counterparty', header: 'Contraparte', width: 'minmax(160px, 1.5fr)', cell: (t) => t.counterparty ?? '—' },
      {
        id: 'match',
        header: 'Conciliación',
        width: 120,
        cell: (t) => {
          const m = links.matchOf(t.id)
          return m ? <Badge tone={MATCH_STATUS[m.status].tone} variant="outline" dot>{MATCH_STATUS[m.status].label}</Badge> : <Mono muted>—</Mono>
        },
        sortValue: (t) => links.matchOf(t.id)?.status,
      },
      { id: 'amount', header: 'Importe', width: 150, align: 'right', cell: (t) => <Amount cents={t.amountCents} currency={t.currency} colorize />, sortValue: (t) => t.amountCents },
    ],
    search: (t) => `${t.id} ${t.description} ${t.counterparty ?? ''} ${t.counterpartyIban ?? ''}`,
    facet: { label: 'Conciliación', value: (t, links) => MATCH_STATUS[links.matchOf(t.id)?.status ?? 'unmatched'].label },
    detail: (t, links) => {
      const m = links.matchOf(t.id)
      return [
        { label: 'Transacción', value: t.id, mono: true },
        { label: 'Sociedad', value: name(links, { kind: 'entity', id: t.entityId }) },
        { label: 'Cuenta', value: t.accountIban, mono: true },
        { label: 'Fecha', value: formatDate(t.date) },
        { label: 'Contraparte', value: t.counterparty ?? '—' },
        { label: 'IBAN contraparte', value: t.counterpartyIban ?? '—', mono: true },
        { label: 'Importe', value: <Amount cents={t.amountCents} currency={t.currency} colorize /> },
        ...(m
          ? [
              { label: 'Conciliación', value: <Badge tone={MATCH_STATUS[m.status].tone} variant="outline" dot>{MATCH_STATUS[m.status].label}</Badge> },
              { label: 'Regla', value: m.rule, mono: true },
              { label: 'Confianza', value: m.confidence == null ? '—' : formatPercent(m.confidence) },
              { label: 'Diferencia', value: money(m.differenceCents, t.currency) },
            ]
          : []),
      ]
    },
  }),
  define<LedgerEntry>({
    kind: 'ledgerEntries',
    description: 'Apuntes del libro mayor por sociedad, cuenta y asiento.',
    aside: (l) => money(l.debitCents || -l.creditCents, l.currency),
    label: 'Libro mayor',
    path: '/libro-mayor',
    icon: BookOpen,
    title: (l) => `${l.entryId} · ${l.account}`,
    columns: () => [
      { id: 'date', header: 'Fecha', width: 110, cell: (l) => formatDate(l.date), sortValue: (l) => l.date },
      entityCol(),
      { id: 'entry', header: 'Asiento', width: 140, cell: (l) => <Mono>{l.entryId}</Mono>, sortValue: (l) => l.entryId },
      { id: 'account', header: 'Cuenta', width: 'minmax(180px, 1.2fr)', cell: (l) => <span><Mono>{l.account}</Mono> {l.accountName}</span>, sortValue: (l) => l.account },
      { id: 'description', header: 'Concepto', width: 'minmax(220px, 2fr)', cell: (l) => l.description },
      { id: 'debit', header: 'Debe', width: 130, align: 'right', cell: (l) => money(l.debitCents || null, l.currency), sortValue: (l) => l.debitCents },
      { id: 'credit', header: 'Haber', width: 130, align: 'right', cell: (l) => money(l.creditCents || null, l.currency), sortValue: (l) => l.creditCents },
    ],
    search: (l) => `${l.id} ${l.entryId} ${l.account} ${l.accountName ?? ''} ${l.description} ${l.sourceRef ?? ''}`,
    facet: { label: 'Cuenta', value: (l) => `${l.account}${l.accountName ? ` · ${l.accountName}` : ''}` },
    detail: (l, links) => [
      { label: 'Apunte', value: l.id, mono: true },
      { label: 'Asiento', value: l.entryId, mono: true },
      { label: 'Sociedad', value: name(links, { kind: 'entity', id: l.entityId }) },
      { label: 'Fecha', value: formatDate(l.date) },
      { label: 'Cuenta', value: `${l.account}${l.accountName ? ` · ${l.accountName}` : ''}` },
      { label: 'Concepto', value: l.description },
      { label: 'Debe', value: money(l.debitCents, l.currency) },
      { label: 'Haber', value: money(l.creditCents, l.currency) },
      { label: 'Documento origen', value: l.sourceRef ?? '—', mono: true },
    ],
  }),
  define<ErpEvent>({
    kind: 'erpEvents',
    description: 'Cambios que registró el ERP, como altas o cambios de IBAN.',
    aside: (e) => formatDate(e.at.slice(0, 10)),
    label: 'Historial del ERP',
    path: null,
    icon: History,
    title: (e) => `${erpActionLabel(e.action)}${e.field ? ` de ${e.field}` : ''} · ${e.subject.id}`,
    columns: () => [
      { id: 'at', header: 'Fecha', width: 170, cell: (e) => formatDateTime(e.at), sortValue: (e) => e.at },
      entityCol(),
      { id: 'subject', header: 'Objeto', width: 160, cell: (e) => <Mono>{e.subject.id}</Mono> },
      { id: 'action', header: 'Acción', width: 'minmax(160px, 1fr)', cell: (e) => `${erpActionLabel(e.action)}${e.field ? ` de ${e.field}` : ''}` },
      { id: 'user', header: 'Usuario', width: 160, cell: (e) => e.user ?? '—' },
    ],
    search: (e) => `${e.id} ${e.subject.id} ${e.action} ${e.field ?? ''} ${e.user ?? ''}`,
    detail: (e) => [
      { label: 'Evento', value: e.id, mono: true },
      { label: 'Fecha', value: formatDateTime(e.at) },
      { label: 'Usuario', value: e.user ?? '—' },
      { label: 'Acción', value: erpActionLabel(e.action) },
      { label: 'Campo', value: e.field ?? '—', mono: true },
      { label: 'Antes', value: e.before ?? '—', mono: true },
      { label: 'Después', value: e.after ?? '—', mono: true },
    ],
  }),
]

/** Kinds with a page, in sidebar order. */
export const PAGE_VIEWS = VIEWS.filter((v) => v.path !== null)

export const viewOf = (kind: DatasetKind) => VIEWS.find((v) => v.kind === kind)!

export const viewOfObject = (kind: ObjectKind) => VIEWS.find((v) => KIND_OF[v.kind] === kind)!
