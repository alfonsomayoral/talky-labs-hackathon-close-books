// Side panel for any object of the package (?ver=kind:id): its details, the agent's alerts on it,
// the objects it links to and its ERP history.
import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Badge, EmptyState, KeyValue, Mono, SidePanel, TabPanel, Tabs } from '@/components'
import { ALERT_TYPE, OBJECT_LABEL, SEVERITY, parseRefKey, refKey, useData, viewOfObject } from '@/data'
import type { Alert, ObjectRef } from '@/domain'
import { formatDateTime } from '@/lib/format'
import { useOpenObject } from '@/lib/urlState'
import { AlertCard } from './AlertCard'
import styles from './ObjectPanel.module.css'

type Tab = 'detail' | 'related' | 'history'

export function ObjectPanelHost() {
  const [key, setKey] = useOpenObject()
  const ref = key ? parseRefKey(key) : null
  return (
    <SidePanel open={!!ref} onClose={() => setKey(null)} storageKey="panel-width" aria-label="Detalle del objeto">
      {ref && <ObjectPanel key={refKey(ref)} target={ref} onOpen={(r) => setKey(refKey(r))} />}
    </SidePanel>
  )
}

function ObjectPanel({ target, onOpen }: { target: ObjectRef; onOpen: (r: ObjectRef) => void }) {
  const links = useData((s) => s.links)!
  const [tab, setTab] = useState<Tab>('detail')
  const object = links.get(target)
  if (!object) {
    return <EmptyState title="Este objeto no está en los datos cargados" description={<Mono>{refKey(target)}</Mono>} />
  }
  const view = viewOfObject(target.kind)
  const alerts = links.alertsOf(target)
  const related = links.related(target)
  const history = links.historyOf(target)

  return (
    <div className={styles.panel}>
      <header className={styles.header}>
        <div className={styles.eyebrow}>
          <view.icon aria-hidden />
          <span>{OBJECT_LABEL[target.kind]}</span>
          <Mono muted>{target.id}</Mono>
        </div>
        <h2 className={styles.title}>{view.title(object, links)}</h2>
        {alerts.length > 0 && (
          <div className={styles.badges}>
            {alerts.map((a) => (
              <Badge key={a.id} tone={SEVERITY[a.severity].tone} icon={<AlertTriangle aria-hidden />}>
                {ALERT_TYPE[a.type]}
              </Badge>
            ))}
          </div>
        )}
      </header>
      <Tabs
        idPrefix="obj"
        value={tab}
        onChange={(t) => setTab(t as Tab)}
        aria-label="Secciones"
        tabs={[
          { id: 'detail', label: 'Detalle' },
          { id: 'related', label: 'Relacionados', count: related.length },
          { id: 'history', label: 'Historial', count: history.length },
        ]}
      />
      <TabPanel idPrefix="obj" id={tab} className={styles.body}>
        {tab === 'detail' && (
          <div className={styles.stack}>
          {alerts.map((a: Alert) => (
            <AlertCard key={a.id} alert={a} subject={target} onOpen={onOpen} />
          ))}
          <KeyValue items={view.detail(object, links)} />
          </div>
        )}
        {tab === 'related' &&
          (related.length === 0 ? (
            <EmptyState size="sm" title="Sin objetos relacionados" />
          ) : (
            <ul className={styles.list}>
              {related.map((r) => {
                const v = viewOfObject(r.kind)
                return (
                  <li key={refKey(r)}>
                    <button type="button" className={styles.row} onClick={() => onOpen(r)}>
                      <v.icon aria-hidden className={styles.rowIcon} />
                      <span className={styles.rowKind}>{OBJECT_LABEL[r.kind]}</span>
                      <span className={styles.rowTitle}>{v.title(links.get(r)!, links)}</span>
                      <Mono muted>{r.id}</Mono>
                    </button>
                  </li>
                )
              })}
            </ul>
          ))}
        {tab === 'history' &&
          (history.length === 0 ? (
            <EmptyState size="sm" title="El ERP no registra cambios de este objeto" />
          ) : (
            <ol className={styles.timeline}>
              {history.map((e) => (
                <li key={e.id} className={styles.event}>
                  <div className={styles.eventHead}>
                    <span className={styles.eventAction}>
                      {e.action}
                      {e.field && (
                        <>
                          {' · '}
                          <Mono>{e.field}</Mono>
                        </>
                      )}
                    </span>
                    <span className={styles.eventMeta}>
                      {formatDateTime(e.at)} · {e.user ?? 'sin usuario'}
                    </span>
                  </div>
                  {(e.before != null || e.after != null) && (
                    <div className={styles.diff}>
                      <Mono className={styles.before}>{e.before ?? '—'}</Mono>
                      <span aria-hidden>→</span>
                      <Mono className={styles.after}>{e.after ?? '—'}</Mono>
                    </div>
                  )}
                </li>
              ))}
            </ol>
          ))}
      </TabPanel>
    </div>
  )
}
