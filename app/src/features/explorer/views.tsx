// What each explorer type shows: its hook, its columns and its panel. A new type is a spec in
// data/registry/explorer.ts plus one entry here.
import type { ComponentType } from 'react'
import { Amount, Badge, Mono, type Column } from '@/components'
import { useDataDocuments, useDataItems, useDataParties, useDetailFiles, type ExplorerSpec, type PagedList } from '@/data'
import type { DataItem, DetailFileRow, DocumentRow, Party } from '@/domain'
import { formatDate, formatMonth, formatNumber } from '@/lib/format'
import { facetLabel } from './facetLabel'
import { DocumentPanel, ItemPanel, PartyPanel, type PanelProps } from './panels'

type Params = Parameters<typeof useDataItems>[1]

export interface ExplorerView<T> {
  useRows: (phase: string, params: Params) => PagedList<T>
  columns: Column<T>[]
  rowId: (row: T) => string
  /** Opened by `?ver=`. Types with no panel (detail files) leave it out. */
  panel?: { title: string; Content: ComponentType<PanelProps> }
}

/** Each type has its own row shape; the page only needs them uniformly. */
const view = <T,>(v: ExplorerView<T>) => v as unknown as ExplorerView<unknown>

const items: Column<DataItem>[] = [
  { id: 'documentNumber', header: 'Número', width: 150, cell: (r) => <Mono>{r.documentNumber}</Mono>, sortValue: (r) => r.documentNumber },
  { id: 'itemType', header: 'Tipo', width: 160, cell: (r) => <Badge variant="outline">{facetLabel('items', r.itemType)}</Badge>, sortValue: (r) => r.itemType },
  { id: 'partyName', header: 'Tercero', width: 'minmax(200px, 1fr)', cell: (r) => r.partyName, sortValue: (r) => r.partyName },
  { id: 'entity', header: 'Sociedad', width: 96, cell: (r) => <Mono>{r.entity}</Mono>, sortValue: (r) => r.entity },
  { id: 'issueDate', header: 'Emisión', width: 112, cell: (r) => formatDate(r.issueDate), sortValue: (r) => r.issueDate },
  { id: 'dueDate', header: 'Vencimiento', width: 112, cell: (r) => formatDate(r.dueDate), sortValue: (r) => r.dueDate },
  { id: 'totalCents', header: 'Total', width: 130, align: 'right', cell: (r) => <Amount cents={r.totalCents} currency={r.currency} />, sortValue: (r) => r.totalCents },
  {
    id: 'openAtStartCents',
    header: 'Abierta al inicio',
    width: 140,
    align: 'right',
    cell: (r) => <Amount cents={r.openAtStartCents} currency={r.currency} />,
    sortValue: (r) => r.openAtStartCents,
  },
]

const parties: Column<Party>[] = [
  { id: 'partyId', header: 'Id', width: 120, cell: (r) => <Mono>{r.partyId}</Mono>, sortValue: (r) => r.partyId },
  { id: 'name', header: 'Nombre', width: 'minmax(220px, 1fr)', cell: (r) => r.name, sortValue: (r) => r.name },
  { id: 'kind', header: 'Clase', width: 100, cell: (r) => <Badge variant="outline">{facetLabel('parties', r.kind)}</Badge>, sortValue: (r) => r.kind },
  { id: 'entity', header: 'Sociedad', width: 96, cell: (r) => <Mono>{r.entity}</Mono>, sortValue: (r) => r.entity },
  { id: 'taxId', header: 'NIF', width: 120, cell: (r) => <Mono>{r.taxId ?? '—'}</Mono>, sortValue: (r) => r.taxId },
  { id: 'country', header: 'País', width: 64, cell: (r) => r.country ?? '—', sortValue: (r) => r.country },
  { id: 'paymentTerms', header: 'Condiciones', width: 130, cell: (r) => r.paymentTerms ?? '—', sortValue: (r) => r.paymentTerms },
  { id: 'currency', header: 'Divisa', width: 70, cell: (r) => <Mono>{r.currency ?? '—'}</Mono>, sortValue: (r) => r.currency },
  { id: 'groupId', header: 'Grupo', width: 110, cell: (r) => <Mono>{r.groupId ?? '—'}</Mono>, sortValue: (r) => r.groupId },
  {
    id: 'blockedSince',
    header: 'Bloqueado',
    width: 120,
    cell: (r) => (r.blockedSince ? <Badge tone="danger">{formatDate(r.blockedSince)}</Badge> : '—'),
    sortValue: (r) => r.blockedSince,
  },
]

const documents: Column<DocumentRow>[] = [
  { id: 'name', header: 'Fichero', width: 'minmax(240px, 1.2fr)', cell: (r) => <Mono>{r.name}</Mono>, sortValue: (r) => r.name },
  { id: 'kind', header: 'Clase', width: 150, cell: (r) => <Badge variant="outline">{facetLabel('documents', r.kind)}</Badge>, sortValue: (r) => r.kind },
  { id: 'entity', header: 'Sociedad', width: 96, cell: (r) => <Mono>{r.entity}</Mono>, sortValue: (r) => r.entity },
  { id: 'format', header: 'Formato', width: 80, cell: (r) => <Mono>{r.format}</Mono>, sortValue: (r) => r.format },
  { id: 'date', header: 'Fecha', width: 112, cell: (r) => formatDate(r.date), sortValue: (r) => r.date },
  { id: 'partyName', header: 'Tercero o pagador', width: 'minmax(180px, 1fr)', cell: (r) => r.partyName ?? '—', sortValue: (r) => r.partyName },
]

const detailFiles: Column<DetailFileRow>[] = [
  { id: 'path', header: 'Fichero', width: 'minmax(260px, 1.5fr)', cell: (r) => <Mono>{r.path}</Mono>, sortValue: (r) => r.path },
  { id: 'kind', header: 'Clase', width: 180, cell: (r) => <Badge variant="outline">{facetLabel('detailFiles', r.kind)}</Badge>, sortValue: (r) => r.kind },
  { id: 'entity', header: 'Sociedad', width: 96, cell: (r) => <Mono>{r.entity}</Mono>, sortValue: (r) => r.entity },
  { id: 'month', header: 'Mes', width: 100, cell: (r) => formatMonth(r.month), sortValue: (r) => r.month },
  { id: 'rows', header: 'Filas', width: 90, align: 'right', cell: (r) => formatNumber(r.rows), sortValue: (r) => r.rows },
]

export const VIEWS: Record<ExplorerSpec['id'], ExplorerView<unknown>> = {
  items: view<DataItem>({ useRows: useDataItems, columns: items, rowId: (r) => r.itemId, panel: { title: 'Partida', Content: ItemPanel } }),
  parties: view<Party>({ useRows: useDataParties, columns: parties, rowId: (r) => r.partyId, panel: { title: 'Tercero', Content: PartyPanel } }),
  documents: view<DocumentRow>({ useRows: useDataDocuments, columns: documents, rowId: (r) => r.path, panel: { title: 'Documento', Content: DocumentPanel } }),
  detailFiles: view<DetailFileRow>({ useRows: useDetailFiles, columns: detailFiles, rowId: (r) => r.path }),
}
