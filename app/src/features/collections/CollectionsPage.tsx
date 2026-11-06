import { useMemo } from 'react'
import { CircleAlert, CircleCheck } from 'lucide-react'
import { Amount, Badge, Card, DataTable, EmptyState, FilterBar, Metric, Mono, Page, PageHeader, Skeleton, Tooltip, type Column, type SortState } from '@/components'
import { useActiveRun, useAging } from '@/data'
import type { AgingParty } from '@/domain'
import { formatDate, formatNumber, formatPercent } from '@/lib/format'
import { useEntityScope, useOpenObject, useTextParam } from '@/lib/urlState'
import { TextField } from '@/features/shared'
import { AgingBar, AgingLegend } from './AgingBar'
import { PartyPanel } from './PartyPanel'
import { RISK_HEURISTIC, RISK_TONE, filterParties, riskOf, RISK_LABEL, sortFromParam, sortToParam } from './model'
import styles from './CollectionsPage.module.css'

const RISK_RANK = { low: 0, medium: 1, high: 2 }

export function CollectionsPage() {
  const { runId } = useActiveRun()
  const [entity] = useEntityScope()
  const [q, setQ] = useTextParam('q')
  const [orden, setOrden] = useTextParam('orden')
  const [open, setOpen] = useOpenObject()

  const { data: aging, error, isPending } = useAging(runId, entity, 'customer')
  const rows = useMemo(() => filterParties(aging?.parties ?? [], q), [aging, q])

  // The API returns the top 200 by overdue balance: these two are counts over them.
  const disputes = useMemo(() => (aging?.parties ?? []).reduce((n, p) => n + p.disputes, 0), [aging])
  const duplicates = useMemo(() => (aging?.parties ?? []).reduce((n, p) => n + p.duplicates, 0), [aging])

  const columns = useMemo<Column<AgingParty>[]>(
    () => [
      { id: 'partyName', header: 'Cliente', width: 'minmax(180px, 2fr)', sortValue: (p) => p.partyName.toLowerCase(), cell: (p) => <span className={styles.truncate}>{p.partyName}</span> },
      { id: 'entity', header: 'Sociedad', width: 104, sortValue: (p) => p.entity, cell: (p) => <Mono>{p.entity}</Mono> },
      { id: 'overdueEur', header: 'Vencido', width: 120, align: 'right', sortValue: (p) => p.overdueEur, cell: (p) => <Amount cents={p.overdueEur} currency="EUR" compact /> },
      { id: 'buckets', header: 'Tramos', width: 'minmax(120px, 1fr)', cell: (p) => <AgingBar buckets={p.buckets} label={`${p.partyName}: saldo por tramo de vencimiento`} /> },
      { id: 'openItems', header: 'Facturas', width: 96, align: 'right', sortValue: (p) => p.openItems, cell: (p) => <span className="tabular">{formatNumber(p.openItems)}</span> },
      {
        id: 'oldestDaysOverdue',
        header: 'Más antigua',
        width: 124,
        align: 'right',
        sortValue: (p) => p.oldestDaysOverdue,
        cell: (p) => <span className="tabular">{p.oldestDaysOverdue > 0 ? `${formatNumber(p.oldestDaysOverdue)} d` : '—'}</span>,
      },
      { id: 'disputes', header: 'Disputas', width: 100, align: 'right', sortValue: (p) => p.disputes, cell: (p) => <span className="tabular">{p.disputes || '—'}</span> },
      { id: 'duplicates', header: 'Duplicados', width: 112, align: 'right', sortValue: (p) => p.duplicates, cell: (p) => <span className="tabular">{p.duplicates || '—'}</span> },
      {
        id: 'risk',
        header: (
          <Tooltip content={RISK_HEURISTIC}>
            <span>Riesgo</span>
          </Tooltip>
        ),
        width: 100,
        sortValue: (p) => RISK_RANK[riskOf(p)],
        cell: (p) => {
          const risk = riskOf(p)
          return <Badge tone={RISK_TONE[risk]}>{RISK_LABEL[risk]}</Badge>
        },
      },
    ],
    [],
  )

  const onSortChange = (sort: SortState | null) => setOrden(sortToParam(sort))

  let body
  if (error) {
    body = <EmptyState icon={<CircleAlert />} title="No se han podido cargar los cobros" description={error.message} />
  } else if (isPending) {
    body = (
      <div className={styles.loading} aria-busy aria-label="Cargando clientes">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} height={36} />
        ))}
      </div>
    )
  } else if (aging.parties.length === 0) {
    body = <EmptyState icon={<CircleCheck />} title="Ningún cliente con saldo vencido" description="Cuando una factura venza sin cobrarse, el cliente aparecerá aquí." />
  } else {
    body = (
      <DataTable
        aria-label="Clientes con saldo vencido"
        rows={rows}
        columns={columns}
        getRowId={(p) => p.partyId}
        sort={sortFromParam(orden)}
        onSortChange={onSortChange}
        selectedId={open}
        onOpen={(p) => setOpen(p.partyId)}
        globalKeys
        empty={<EmptyState size="sm" icon={<CircleAlert />} title="Ningún cliente coincide con la búsqueda" />}
      />
    )
  }

  return (
    <Page fill>
      <PageHeader
        title="Cobros"
        subtitle="A qué clientes reclamar hoy, cuánto y qué hay abierto con cada uno."
        filters={
          <FilterBar onClear={q ? () => setQ(null) : undefined} end={aging && <span className="tabular">{formatNumber(rows.length)} clientes</span>}>
            <TextField label="Buscar clientes" hideLabel type="search" placeholder="Buscar por cliente, id o sociedad" value={q ?? ''} onChange={(v) => setQ(v || null)} className={styles.search} />
          </FilterBar>
        }
      />
      <Card padding="md">
        <div className={styles.metrics}>
          <Metric
            label="Saldo abierto"
            value={aging ? <Amount cents={aging.openEur} currency="EUR" compact /> : '—'}
            loading={isPending}
            comparison={aging ? `a ${formatDate(aging.asOf)}` : undefined}
          />
          <Metric
            label="Vencido"
            value={aging ? <Amount cents={aging.overdueEur} currency="EUR" compact /> : '—'}
            loading={isPending}
            comparison={aging && aging.openEur > 0 ? `${formatPercent(aging.overdueEur / aging.openEur)} del saldo` : undefined}
          />
          <Metric label="Disputas abiertas" value={aging ? formatNumber(disputes) : '—'} loading={isPending} hint="Suma de los 200 clientes con más saldo vencido." />
          <Metric label="Duplicados a devolver" value={aging ? formatNumber(duplicates) : '—'} loading={isPending} hint="Suma de los 200 clientes con más saldo vencido." />
        </div>
        {aging && (
          <div className={styles.aging}>
            <AgingBar buckets={aging.totals} label="Saldo del grupo por tramo de vencimiento" size="md" />
            <AgingLegend buckets={aging.totals} />
          </div>
        )}
      </Card>
      {body}
      <PartyPanel runId={runId} partyId={open} aging={aging?.parties ?? []} onClose={() => setOpen(null)} />
    </Page>
  )
}
