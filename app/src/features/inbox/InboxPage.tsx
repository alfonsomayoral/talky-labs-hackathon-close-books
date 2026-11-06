import { useMemo, useRef, useState } from 'react'
import { CircleAlert, CircleCheck } from 'lucide-react'
import { Amount, Badge, DataTable, EmptyState, FilterBar, FilterChip, Mono, Page, PageHeader, Skeleton, type Column, type SortState } from '@/components'
import { useActiveRun, useCases, useRunStats } from '@/data'
import { CASE_STATUS_LABEL, INBOX_STATUSES, PRIORITY_LABEL, caseKindLabel, type CasePriority, type CaseRow } from '@/domain'
import { formatNumber } from '@/lib/format'
import { useEntityScope, useListParam, useOpenObject, useTextParam } from '@/lib/urlState'
import { ACTION_LABEL, TextField } from '@/features/shared'
import { CasePanel } from './CasePanel'
import { DEFAULT_SORT, ageDays, ageLabel, queueStatuses, sortFromParam, sortToParam } from './model'
import styles from './InboxPage.module.css'

const PRIORITY_TONE = { 1: 'danger', 2: 'warn', 3: 'neutral' } as const
const ROW_HEIGHT = 60
const SEARCH_DEBOUNCE_MS = 300

const PRIORITY_OPTIONS = (['1', '2', '3'] as const).map((p) => ({ value: p, label: PRIORITY_LABEL[Number(p) as CasePriority] }))
const STATE_OPTIONS = INBOX_STATUSES.map((s) => ({ value: s, label: CASE_STATUS_LABEL[s] }))

export function InboxPage() {
  const { runId, run } = useActiveRun()
  const [entity] = useEntityScope()
  const [kinds, setKinds] = useListParam('kind')
  const [priorities, setPriorities] = useListParam('prioridad')
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
    status: queueStatuses(states),
    kind: kinds.join(','),
    priority: priorities.join(','),
    entity,
    q,
    sort: orden ?? DEFAULT_SORT,
  })

  const kindOptions = useMemo(() => {
    const known = (stats?.byKind ?? []).map((k) => k.kind)
    return [...new Set([...known, ...kinds])].map((kind) => ({ value: kind, label: caseKindLabel(kind) }))
  }, [stats, kinds])

  const asOf = stats?.periodTo ?? run.createdAt
  const columns = useMemo<Column<CaseRow>[]>(
    () => [
      {
        id: 'priority',
        header: 'Prioridad',
        width: 96,
        sortValue: (c) => c.priority,
        cell: (c) => <Badge tone={PRIORITY_TONE[c.priority]}>{PRIORITY_LABEL[c.priority]}</Badge>,
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
      { id: 'entity', header: 'Sociedad', width: 80, cell: (c) => <Mono>{c.entity}</Mono> },
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
        width: 100,
        align: 'right',
        sortValue: (c) => c.bookingDate,
        cell: (c) => <span className="tabular">{ageLabel(ageDays(c.bookingDate, asOf))}</span>,
      },
      { id: 'action', header: 'Acción sugerida', width: 'minmax(130px, 1fr)', cell: (c) => <span className={styles.truncate}>{ACTION_LABEL[c.suggestedAction]}</span> },
    ],
    [asOf],
  )

  const filtered = kinds.length > 0 || priorities.length > 0 || states.length > 0 || q != null
  const clear = () => {
    setKinds([])
    setPriorities([])
    setStates([])
    setQ(null)
    setTyped('')
    window.clearTimeout(timer.current)
  }
  const onSortChange = (sort: SortState | null) => setOrden(sortToParam(sort))

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
        empty={<EmptyState size="sm" icon={<CircleAlert />} title="Ningún caso coincide con los filtros" />}
      />
    )
  }

  return (
    <Page fill>
      <PageHeader
        title="Te necesitan"
        subtitle="Los casos que esperan a una persona, por prioridad e importe."
        filters={
          <FilterBar onClear={filtered ? clear : undefined} end={cases.total != null && <span className="tabular">{formatNumber(cases.total)} casos</span>}>
            <TextField label="Buscar casos" hideLabel type="search" placeholder="Buscar por caso, resumen o tercero" value={typed} onChange={search} className={styles.search} />
            <FilterChip label="Tipo" options={kindOptions} selected={kinds} onChange={setKinds} />
            <FilterChip label="Prioridad" options={PRIORITY_OPTIONS} selected={priorities} onChange={setPriorities} />
            <FilterChip label="Estado" options={STATE_OPTIONS} selected={states} onChange={setStates} />
          </FilterBar>
        }
      />
      {body}
      <CasePanel runId={runId} caseId={open} onClose={() => setOpen(null)} />
    </Page>
  )
}
