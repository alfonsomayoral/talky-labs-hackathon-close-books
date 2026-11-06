// One page per kind of the registry: title with what the rows are, a search and one facet,
// and the rows in a virtualized table inside a card. A row opens the object panel.
import { useMemo, useState } from 'react'
import { AlertTriangle, Search, X } from 'lucide-react'
import { Button, DataTable, FilterChip, Tooltip, type Column } from '@/components'
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

  const withAlerts = useMemo(() => scoped.filter((o) => links.alertsOf({ kind, id: o.id }).some((a) => a.subject.id === o.id)).length, [scoped, links, kind])

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
        width: 36,
        align: 'center',
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
  const noun = view.label.toLowerCase()

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>{view.label}</h1>
        <p className={styles.sub}>
          {formatNumber(scoped.length)} {noun} en {entity ? `la sociedad ${entity}` : 'todo el grupo'}
          {withAlerts > 0 && (
            <>
              {' · '}
              <span className={styles.withAlerts}>{formatNumber(withAlerts)} con alertas del agente</span>
            </>
          )}
          {' · '}
          {view.description}
        </p>
      </header>
      <div className={styles.toolbar}>
        <label className={styles.search}>
          <Search aria-hidden className={styles.searchIcon} />
          <input type="search" placeholder={`Buscar en ${noun}…`} value={query} onChange={(e) => setQuery(e.target.value)} aria-label={`Buscar en ${noun}`} />
        </label>
        {view.facet && <FilterChip label={view.facet.label} options={facetOptions} selected={facet} onChange={setFacet} />}
        {filtered && (
          <Button variant="ghost" size="sm" leadingIcon={<X />} onClick={() => (setQuery(''), setFacet([]))}>
            Limpiar
          </Button>
        )}
        <span className={styles.count}>{filtered ? `${formatNumber(rows.length)} de ${formatNumber(scoped.length)}` : `${formatNumber(rows.length)} filas`}</span>
      </div>
      <div className={styles.tableCard}>
        <DataTable rows={rows} columns={columns} getRowId={(o) => o.id} globalKeys onOpen={(o) => setOpenKey(refKey({ kind, id: o.id }))} aria-label={view.label} />
      </div>
    </div>
  )
}
