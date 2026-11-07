import { useMemo, useRef, useState } from 'react'
import { CircleAlert, CircleCheck } from 'lucide-react'
import { Amount, Badge, Button, Card, DataTable, EmptyState, FilterBar, FilterChip, Metric, Mono, Page, PageHeader, Skeleton, TabPanel, Tabs, type Column, type SortState } from '@/components'
import { useActiveRun, useCases, useQueueTotals, useRunStats } from '@/data'
import { PRIORITY_LABEL, QUEUES, caseKindLabel, firstActionable, queueFilter, queueOfKind, type CasePriority, type CaseRow } from '@/domain'
import { formatNumber } from '@/lib/format'
import { useEntityScope, useListParam, useOpenObject, useTextParam } from '@/lib/urlState'
import { ACTION_LABEL, TextField } from '@/features/shared'
import { CasePanel } from './CasePanel'
import { DEFAULT_SORT, ageDays, ageLabel, sortFromParam, sortToParam } from './model'
import styles from './InboxPage.module.css'

const PRIORITY_EMPHASIS = { 1: 'strong', 2: 'medium', 3: 'quiet' } as const
const ROW_HEIGHT = 60
const SEARCH_DEBOUNCE_MS = 300

const PRIORITY_OPTIONS = (['1', '2', '3'] as const).map((p) => ({ value: p, label: PRIORITY_LABEL[Number(p) as CasePriority] }))
const ID_PREFIX = 'inbox'

export function InboxPage() {
  const { runId, run } = useActiveRun()
  const [entity] = useEntityScope()
  const [chosenKinds, setKinds] = useListParam('kind')
  const [priorities, setPriorities] = useListParam('prioridad')
  const [vista, setVista] = useTextParam('vista')
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

  const queue = QUEUES.find((t) => t.id === vista) ?? QUEUES[0]
  // A kind left in the URL by another tab does not filter this one.
  const kinds = queue.id === 'decidir' ? [] : chosenKinds.filter((k) => queueOfKind(k) === queue.id)
  const filter = queueFilter(queue.id)

  const stats = useRunStats(runId, entity).data
  const totals = useQueueTotals(runId, entity)
  const cases = useCases(runId, {
    status: filter.status,
    kind: kinds.join(',') || filter.kind,
    priority: priorities.join(','),
    entity,
    q,
    sort: orden ?? DEFAULT_SORT,
  })

  const kindOptions = useMemo(() => {
    const known = (stats?.byKind ?? []).map((k) => k.kind).filter((k) => queueOfKind(k) === queue.id)
    return [...new Set([...known, ...kinds])].map((kind) => ({ value: kind, label: caseKindLabel(kind) }))
  }, [stats, kinds, queue.id])

  const asOf = stats?.periodTo ?? run.createdAt
  const columns = useMemo<Column<CaseRow>[]>(
    () => [
      {
        id: 'priority',
        header: 'Prioridad',
        width: 104,
        sortValue: (c) => c.priority,
        cell: (c) => <Badge emphasis={PRIORITY_EMPHASIS[c.priority]}>{PRIORITY_LABEL[c.priority]}</Badge>,
      },
      {
        id: 'case',
        header: 'Caso',
        width: 'minmax(260px, 3fr)',
        cell: (c) => (
          <span className={styles.twoLines}>
            <span className={styles.kind}>{caseKindLabel(c.kind)}</span>
            <span className={styles.summary}>{c.summary}</span>
          </span>
        ),
      },
      { id: 'party', header: 'Tercero', width: 'minmax(120px, 1.2fr)', cell: (c) => <span className={styles.truncate}>{c.partyName ?? '—'}</span> },
      { id: 'entity', header: 'Sociedad', width: 92, cell: (c) => <Mono>{c.entity}</Mono> },
      {
        id: 'amountEur',
        header: 'Importe',
        width: 150,
        align: 'right',
        sortValue: (c) => c.amountEur,
        cell: (c) => (
          <span className={styles.amount}>
            <Amount cents={c.amountCents} currency={c.currency} />
            {c.currency !== 'EUR' && (
              <span className={styles.amountEur}>
                <Amount cents={c.amountEur} currency="EUR" />
              </span>
            )}
          </span>
        ),
      },
      {
        id: 'bookingDate',
        header: 'Antigüedad',
        width: 112,
        align: 'right',
        sortValue: (c) => c.bookingDate,
        cell: (c) => <span className="tabular">{ageLabel(ageDays(c.bookingDate, asOf))}</span>,
      },
      { id: 'action', header: 'Acción sugerida', width: 'minmax(130px, 1fr)', cell: (c) => <span className={styles.truncate}>{ACTION_LABEL[c.suggestedAction]}</span> },
    ],
    [asOf],
  )

  // Every decision is the same kind of work on a movement with no party yet: those two columns say nothing there.
  const shownColumns = queue.id === 'decidir' ? columns.filter((c) => c.id !== 'party' && c.id !== 'action') : columns

  const filtered = kinds.length > 0 || priorities.length > 0 || q != null
  const clear = () => {
    setKinds([])
    setPriorities([])
    setQ(null)
    setTyped('')
    window.clearTimeout(timer.current)
  }
  const onSortChange = (sort: SortState | null) => setOrden(sortToParam(sort))
  const first = firstActionable(queue.id, cases.rows)

  let body
  if (cases.error) {
    body = <EmptyState icon={<CircleAlert />} title="No se han podido cargar los casos" description={cases.error.message} />
  } else if (cases.loading) {
    body = (
      <div className={styles.loading} aria-busy aria-label="Cargando casos">
        {Array.from({ length: 7 }, (_, i) => (
          <Skeleton key={i} height={ROW_HEIGHT} radius="var(--radius-md)" />
        ))}
      </div>
    )
  } else if (cases.rows.length === 0 && !filtered) {
    body = (
      <EmptyState
        icon={<CircleCheck />}
        title="Nada pendiente: el sistema ha cerrado todo lo demás"
        description="Cuando un caso necesite a una persona, aparecerá aquí."
      />
    )
  } else {
    body = (
      <DataTable
        aria-label="Casos pendientes"
        rowHeight={ROW_HEIGHT}
        rows={cases.rows}
        columns={shownColumns}
        getRowId={(c) => c.caseId}
        serverSort
        sort={sortFromParam(orden)}
        onSortChange={onSortChange}
        onEndReached={cases.loadMore}
        selectedId={open}
        onSelectedChange={(id) => open && id && setOpen(id)}
        onOpen={(c) => setOpen(c.caseId)}
        globalKeys
        empty={<EmptyState size="sm" icon={<CircleAlert />} title="Ningún caso coincide con los filtros" />}
      />
    )
  }

  return (
    <Page fill>
      <PageHeader
        title="Te necesitan"
        subtitle={queue.description}
        actions={
          <Button variant="primary" disabled={!first} onClick={() => first && setOpen(first.caseId)}>
            {queue.primary}
          </Button>
        }
      />
      <div className={styles.kpis}>
        {QUEUES.map((t) => (
          <button key={t.id} type="button" className={styles.kpi} data-surface={t.id === queue.id ? 'feature' : undefined} aria-pressed={t.id === queue.id} onClick={() => setVista(t.id)}>
            <Metric
              label={t.label}
              value={totals ? formatNumber(totals[t.id].cases) : ''}
              loading={!totals}
              comparison={totals ? <Amount cents={totals[t.id].amountEur} compact /> : undefined}
            />
          </button>
        ))}
      </div>
      <Tabs
        aria-label="Tipo de trabajo"
        tabs={QUEUES.map((t) => ({ id: t.id, label: t.label, count: totals?.[t.id].cases }))}
        value={queue.id}
        onChange={setVista}
        idPrefix={ID_PREFIX}
      />
      <TabPanel idPrefix={ID_PREFIX} id={queue.id} className={styles.panel}>
        <FilterBar onClear={filtered ? clear : undefined} end={cases.total != null && <span className="tabular">{formatNumber(cases.total)} casos</span>}>
          <TextField label="Buscar casos" hideLabel type="search" placeholder="Buscar por caso, resumen o tercero" value={typed} onChange={search} className={styles.search} />
          {queue.id !== 'decidir' && <FilterChip label="Tipo" options={kindOptions} selected={kinds} onChange={setKinds} />}
          <FilterChip label="Prioridad" options={PRIORITY_OPTIONS} selected={priorities} onChange={setPriorities} />
        </FilterBar>
        <Card padding="none" className={styles.tableCard}>
          {body}
        </Card>
      </TabPanel>
      <CasePanel runId={runId} caseId={open} onClose={() => setOpen(null)} />
    </Page>
  )
}
