import { useMemo, useRef, useState } from 'react'
import { CircleAlert, CircleCheck } from 'lucide-react'
import { Amount, Badge, Card, DataTable, EmptyState, FilterBar, FilterChip, Metric, Mono, Page, PageHeader, Skeleton, type Column, type SortState } from '@/components'
import { useActiveRun, useCases, useRunStats } from '@/data'
import { CASE_STATUS_LABEL, caseKindLabel, type CaseRow } from '@/domain'
import { formatMoney, formatNumber } from '@/lib/format'
import { useEntityScope, useListParam, useOpenObject, useTextParam } from '@/lib/urlState'
import { TextField } from '@/features/shared'
import { AgingStrip } from './AgingStrip'
import { CasePanel } from './CasePanel'
import { DEFAULT_SORT, SUPPLIER_KINDS, SUPPLIER_STATUSES, ageDays, ageLabel, emailState, listKinds, listStatuses, TOP_CASES, affectedAmount, sortFromParam, sortToParam, type EmailState } from './model'
import styles from './SuppliersPage.module.css'

const ROW_HEIGHT = 60
const SEARCH_DEBOUNCE_MS = 300
const OPEN_STATUSES = listStatuses([])

const KIND_OPTIONS = SUPPLIER_KINDS.map((kind) => ({ value: kind, label: caseKindLabel(kind) }))
const STATE_OPTIONS = SUPPLIER_STATUSES.map((s) => ({ value: s, label: CASE_STATUS_LABEL[s] }))
const EMAIL_LABEL: Record<EmailState, { tone: 'neutral' | 'info' | 'ok'; label: string }> = {
  none: { tone: 'neutral', label: 'Sin correo' },
  draft: { tone: 'info', label: 'Con correo' },
  closed: { tone: 'ok', label: 'Gestionado' },
}

export function SuppliersPage() {
  const { runId, run } = useActiveRun()
  const [entity] = useEntityScope()
  const [kinds, setKinds] = useListParam('tipo')
  const [states, setStates] = useListParam('estado')
  const [q, setQ] = useTextParam('q')
  const [orden, setOrden] = useTextParam('orden')
  const [open, setOpen] = useOpenObject()

  // The box answers at once; the API is asked once typing pauses.
  const [typed, setTyped] = useState(q ?? '')
  const timer = useRef<number>(undefined)
  const search = (value: string) => {
    setTyped(value)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setQ(value.trim() || null), SEARCH_DEBOUNCE_MS)
  }

  const stats = useRunStats(runId, entity).data
  const cases = useCases(runId, {
    status: listStatuses(states),
    kind: listKinds(kinds),
    entity,
    q,
    sort: orden ?? DEFAULT_SORT,
  })
  // Header figures ignore the search and the facets: they are what is open for the scope.
  const openAll = useCases(runId, { status: OPEN_STATUSES, kind: SUPPLIER_KINDS.join(','), entity, sort: '-amountEur', size: TOP_CASES })
  const openCredits = useCases(runId, { status: OPEN_STATUSES, kind: 'supplier_credit_pending', entity, size: 1 })
  const affected = affectedAmount(openAll.rows, openAll.total)

  const asOf = stats?.periodTo ?? run.createdAt
  const columns = useMemo<Column<CaseRow>[]>(
    () => [
      {
        id: 'partyName',
        header: 'Proveedor',
        width: 'minmax(180px, 1.4fr)',
        sortValue: (c) => c.partyName ?? '',
        cell: (c) => (
          <span className={styles.twoLines}>
            <span className={styles.name}>{c.partyName ?? '—'}</span>
            <Mono muted>{c.itemIds.length === 0 ? '—' : c.itemIds.length === 1 ? c.itemIds[0] : `${c.itemIds[0]} +${c.itemIds.length - 1}`}</Mono>
          </span>
        ),
      },
      {
        id: 'kind',
        header: 'Incidencia',
        width: 'minmax(280px, 3fr)',
        sortValue: (c) => c.kind,
        cell: (c) => (
          <span className={styles.twoLines}>
            <span className={styles.summary}>{c.summary}</span>
            <span className={styles.kind}>{caseKindLabel(c.kind)}</span>
          </span>
        ),
      },
      { id: 'entity', header: 'Sociedad', width: 80, cell: (c) => <Mono>{c.entity}</Mono> },
      {
        id: 'amountEur',
        header: 'Importe',
        width: 120,
        align: 'right',
        sortValue: (c) => c.amountEur,
        cell: (c) => <Amount cents={c.amountEur} currency="EUR" />,
      },
      {
        id: 'bookingDate',
        header: 'Antigüedad',
        width: 100,
        align: 'right',
        sortValue: (c) => c.bookingDate,
        cell: (c) => <span className="tabular">{ageLabel(ageDays(c.bookingDate, asOf))}</span>,
      },
      {
        id: 'email',
        header: 'Correo',
        width: 116,
        cell: (c) => {
          const state = EMAIL_LABEL[emailState(c)]
          return <Badge tone={state.tone}>{state.label}</Badge>
        },
      },
    ],
    [asOf],
  )

  const filtered = kinds.length > 0 || states.length > 0 || q != null
  const clear = () => {
    setKinds([])
    setStates([])
    setQ(null)
    setTyped('')
    window.clearTimeout(timer.current)
  }
  const onSortChange = (sort: SortState | null) => setOrden(sortToParam(sort))

  let body
  if (cases.error) {
    body = <EmptyState icon={<CircleAlert />} title="No se han podido cargar las incidencias" description={cases.error.message} />
  } else if (cases.loading) {
    body = (
      <div className={styles.loading} aria-busy aria-label="Cargando incidencias">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} height={ROW_HEIGHT} radius="var(--radius-md)" />
        ))}
      </div>
    )
  } else if (cases.rows.length === 0 && !filtered) {
    body = <EmptyState icon={<CircleCheck />} title="Ningún proveedor tiene incidencias abiertas" description="Cuando una factura se pague por otro importe o quede un abono sin compensar, aparecerá aquí." />
  } else {
    body = (
      <DataTable
        aria-label="Incidencias con proveedores"
        variant="cards"
        rowHeight={ROW_HEIGHT}
        rows={cases.rows}
        columns={columns}
        getRowId={(c) => c.caseId}
        serverSort
        sort={sortFromParam(orden)}
        onSortChange={onSortChange}
        onEndReached={cases.loadMore}
        selectedId={open}
        onOpen={(c) => setOpen(c.caseId)}
        globalKeys
        empty={<EmptyState size="sm" icon={<CircleAlert />} title="Ninguna incidencia coincide con los filtros" />}
      />
    )
  }

  const loadingHeader = openAll.loading || openCredits.loading

  return (
    <Page fill>
      <PageHeader
        title="Proveedores"
        subtitle="Facturas pagadas por otro importe, dos veces, rechazadas, cedidas a un factor o abonos sin compensar."
        filters={
          <FilterBar onClear={filtered ? clear : undefined} end={cases.total != null && <span className="tabular">{formatNumber(cases.total)} incidencias</span>}>
            <TextField label="Buscar incidencias" hideLabel type="search" placeholder="Buscar proveedor o caso" value={typed} onChange={search} className={styles.search} />
            <FilterChip label="Incidencia" options={KIND_OPTIONS} selected={kinds} onChange={setKinds} />
            <FilterChip label="Estado" options={STATE_OPTIONS} selected={states} onChange={setStates} />
          </FilterBar>
        }
      />
      <div className={styles.header}>
        <div className={styles.metrics}>
        <Card>
          <Metric label="Incidencias abiertas" value={loadingHeader ? '' : formatNumber(openAll.total)} loading={loadingHeader} />
        </Card>
        <Card>
          <Metric
            label={affected.label}
            value={loadingHeader ? '' : formatMoney(affected.cents, 'EUR', { compact: true })}
            loading={loadingHeader}
          />
        </Card>
        <Card>
          <Metric
            label="Abonos por compensar"
            value={loadingHeader ? '' : formatNumber(openCredits.total)}
            loading={loadingHeader}
          />
        </Card>
        </div>
        <AgingStrip runId={runId} entity={entity} />
      </div>
      {body}
      <CasePanel runId={runId} caseId={open} onClose={() => setOpen(null)} />
    </Page>
  )
}
