import { useMemo } from 'react'
import { useSearchParams } from 'react-router'
import { CloudOff, SearchX } from 'lucide-react'
import { Card, DataTable, EmptyState, FilterBar, FilterChip, Page, PageHeader, SidePanel, Skeleton, TabPanel, Tabs, type SortState } from '@/components'
import { EXPLORER_SPECS, useActiveRun, type ExplorerSpec } from '@/data'
import { formatNumber } from '@/lib/format'
import { useEntityScope, useListParam, useOpenObject, useTextParam } from '@/lib/urlState'
import { SearchBox } from './SearchBox'
import { fromSortParam, switchTab, toSortParam } from './model'
import { VIEWS } from './views'
import styles from './ExplorerPage.module.css'

const TABS = EXPLORER_SPECS.map((s) => ({ id: s.id, label: s.label }))

function ExplorerList({ spec, phase, runId }: { spec: ExplorerSpec; phase: string; runId: string }) {
  const view = VIEWS[spec.id]
  const [entity] = useEntityScope()
  const [facet, setFacet] = useListParam('filtro')
  const [q, setQ] = useTextParam('q')
  const [order, setOrder] = useTextParam('orden')
  const [open, setOpen] = useOpenObject()

  const list = view.useRows(phase, { entity, q, sort: order, [spec.facet.param]: facet.join(',') })
  const sort = useMemo(() => fromSortParam(order), [order])
  const changeSort = (next: SortState | null) => setOrder(toSortParam(next))
  const filtered = Boolean(q || facet.length)
  const Panel = view.panel?.Content

  return (
    <div className={styles.list}>
      <FilterBar
        onClear={filtered ? () => {
          setQ(null)
          setFacet([])
        } : undefined}
        end={list.total != null && <span className="tabular">{formatNumber(list.total)} resultados</span>}
      >
        <SearchBox key={q ?? ''} value={q ?? ''} onSearch={(v) => setQ(v || null)} placeholder={spec.searchPlaceholder} />
        <FilterChip label={spec.facet.label} options={spec.facet.options} selected={facet} onChange={setFacet} />
      </FilterBar>
      <Card padding="none" className={styles.tableCard}>
        {list.loading ? (
          <div className={styles.loading}>
            <Skeleton lines={8} />
          </div>
        ) : list.error ? (
          <EmptyState icon={<CloudOff />} title={`No se han podido cargar ${spec.label.toLowerCase()}`} description={list.error.message} />
        ) : (
          <DataTable
            aria-label={spec.label}
            rows={list.rows}
            columns={view.columns}
            getRowId={view.rowId}
            sort={sort}
            onSortChange={changeSort}
            serverSort
            onEndReached={list.loadMore}
            selectedId={Panel ? open : undefined}
            onSelectedChange={(id) => open && id && setOpen(id)}
            onOpen={Panel ? (row) => setOpen(view.rowId(row)) : undefined}
            globalKeys
            empty={<EmptyState size="sm" icon={<SearchX />} title="Nada coincide" description={filtered ? 'Prueba con otra búsqueda o quita los filtros.' : 'Esta fase no trae datos de este tipo.'} />}
          />
        )}
      </Card>
      {Panel && (
        <SidePanel open={open != null} onClose={() => setOpen(null)} title={view.panel!.title} aria-label={`Detalle: ${view.panel!.title.toLowerCase()}`} storageKey="explorer-panel">
          {open != null && <Panel id={open} phase={phase} runId={runId} />}
        </SidePanel>
      )}
    </div>
  )
}

export function ExplorerPage() {
  const { phase, runId } = useActiveRun()
  const [params, setParams] = useSearchParams()
  const spec = EXPLORER_SPECS.find((s) => s.id === params.get('tipo')) ?? EXPLORER_SPECS[0]

  return (
    <Page fill>
      <PageHeader title="Explorador" subtitle="Partidas, terceros, documentos y ficheros de detalle del paquete." />
      <Tabs tabs={TABS} value={spec.id} onChange={(id) => setParams(switchTab(params, id))} idPrefix="explorer" aria-label="Tipo de dato" />
      <TabPanel idPrefix="explorer" id={spec.id} className={styles.panel}>
        <ExplorerList key={spec.id} spec={spec} phase={phase} runId={runId} />
      </TabPanel>
    </Page>
  )
}
