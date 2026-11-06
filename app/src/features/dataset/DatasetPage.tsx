// One page per kind of the registry: search, one facet, a virtualized table and the side panel.
import { useMemo, useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { DataTable, FilterBar, FilterChip, Page, PageHeader, Tooltip, type Column } from '@/components'
import { KIND_OF } from '@/domain'
import { ALERT_TYPE, refKey, useData, type AnyObject, type DatasetView } from '@/data'
import { formatNumber } from '@/lib/format'
import { useEntityScope, useOpenObject } from '@/lib/urlState'
import styles from './DatasetPage.module.css'

const normalize = (s: string) =>
  s
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()

export function DatasetPage({ view }: { view: DatasetView }) {
  const dataset = useData((s) => s.dataset)!
  const links = useData((s) => s.links)!
  const [entity] = useEntityScope()
  const [, setOpenKey] = useOpenObject()
  const [query, setQuery] = useState('')
  const [facet, setFacet] = useState<string[]>([])
  const kind = KIND_OF[view.kind]

  const scoped = useMemo(() => {
    const rows = dataset[view.kind] as AnyObject[]
    return entity ? rows.filter((o) => (o.entityId ?? o.id) === entity) : rows
  }, [dataset, view.kind, entity])

  const facetOptions = useMemo(() => {
    if (!view.facet) return []
    const counts = new Map<string, number>()
    for (const o of scoped) {
      const v = view.facet.value(o, links)
      counts.set(v, (counts.get(v) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([value, count]) => ({ value, label: value, count }))
  }, [scoped, view, links])

  const rows = useMemo(() => {
    const q = normalize(query.trim())
    return scoped.filter((o) => (!facet.length || facet.includes(view.facet!.value(o, links))) && (!q || normalize(view.search(o, links)).includes(q)))
  }, [scoped, facet, query, view, links])

  const columns = useMemo<Column<AnyObject>[]>(
    () => [
      {
        id: 'alerts',
        header: '',
        width: 32,
        cell: (o) => {
          const alerts = links.alertsOf({ kind, id: o.id }).filter((a) => a.subject.id === o.id)
          if (!alerts.length) return null
          return (
            <Tooltip content={alerts.map((a) => `${ALERT_TYPE[a.type]}: ${a.title}`).join(' · ')}>
              <AlertTriangle aria-label="Con alertas" className={styles.alert} data-severity={alerts[0].severity} />
            </Tooltip>
          )
        },
      },
      ...view.columns(links),
    ],
    [view, links, kind],
  )

  const filtered = query.trim() !== '' || facet.length > 0

  return (
    <Page fill>
      <PageHeader
        title={view.label}
        subtitle={`${formatNumber(scoped.length)} en ${entity ? `la sociedad ${entity}` : 'todo el grupo'}`}
        filters={
          <FilterBar
            onClear={filtered ? () => (setQuery(''), setFacet([])) : undefined}
            end={filtered ? <span className={styles.count}>{formatNumber(rows.length)} de {formatNumber(scoped.length)}</span> : undefined}
          >
            <input
              type="search"
              className={styles.search}
              placeholder="Buscar…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label={`Buscar en ${view.label.toLowerCase()}`}
            />
            {view.facet && <FilterChip label={view.facet.label} options={facetOptions} selected={facet} onChange={setFacet} />}
          </FilterBar>
        }
      />
      <DataTable
        rows={rows}
        columns={columns}
        getRowId={(o) => o.id}
        globalKeys
        onOpen={(o) => setOpenKey(refKey({ kind, id: o.id }))}
        aria-label={view.label}
      />
    </Page>
  )
}
