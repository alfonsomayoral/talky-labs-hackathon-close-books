// Side panel for any object of the package (?ver=kind:id): its details and the agent's alerts on it,
// the objects it links to, and its ERP history.
import { useState } from 'react'
import { AlertTriangle, ArrowRight, Link2 } from 'lucide-react'
import { Badge, EmptyState, IconButton, KeyValue, Mono, SidePanel, TabPanel, Tabs, toast } from '@/components'
import type { Alert, ObjectKind, ObjectRef } from '@/domain'
import { ALERT_TYPE, OBJECT_LABEL, SEVERITY, erpActionLabel, parseRefKey, refKey, useData, viewOfObject } from '@/data'
import { formatDateTime, formatNumber } from '@/lib/format'
import { useOpenObject } from '@/lib/urlState'
import { AlertCard } from './AlertCard'
import styles from './ObjectPanel.module.css'

type Tab = 'detail' | 'related' | 'history'

export function ObjectPanelHost() {
  const [key, setKey] = useOpenObject()
  const ref = key ? parseRefKey(key) : null
  const copy = () => {
    void navigator.clipboard?.writeText(window.location.href).then(() => toast.success('Enlace copiado'))
  }
  return (
    <SidePanel
      open={!!ref}
      onClose={() => setKey(null)}
      storageKey="panel-width-v2"
      defaultWidth={Math.round(window.innerWidth * 0.4)}
      minWidth={480}
      aria-label="Detalle del objeto"
      title={
        ref && (
          <span className={styles.eyebrow}>
            {OBJECT_LABEL[ref.kind]} <Mono muted>{ref.id}</Mono>
          </span>
        )
      }
      actions={<IconButton icon={<Link2 />} label="Copiar enlace" onClick={copy} />}
    >
      {ref && <ObjectPanel key={refKey(ref)} target={ref} onOpen={(r) => setKey(refKey(r))} />}
    </SidePanel>
  )
}

const KIND_ORDER: ObjectKind[] = ['entity', 'vendor', 'contract', 'purchaseOrder', 'invoice', 'bankTransaction', 'ledgerEntry', 'erpEvent']

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
  const groups = KIND_ORDER.map((k) => ({ kind: k, refs: related.filter((r) => r.kind === k) })).filter((g) => g.refs.length > 0)

  return (
    <div className={styles.panel}>
      <header className={styles.header}>
        <div className={styles.titleRow}>
          <h2 className={styles.title}>{view.title(object, links)}</h2>
          <span className={styles.keyFigure}>{view.aside(object)}</span>
        </div>
        <div className={styles.chips}>
          {object.entityId && <Badge variant="outline">{`Sociedad ${object.entityId}`}</Badge>}
          {alerts.map((a: Alert) => (
            <Badge key={a.id} tone={SEVERITY[a.severity].tone} icon={<AlertTriangle aria-hidden />}>
              {ALERT_TYPE[a.type]}
            </Badge>
          ))}
        </div>
      </header>
      <Tabs
        idPrefix="obj"
        value={tab}
        onChange={(t) => setTab(t as Tab)}
        aria-label="Secciones"
        className={styles.tabs}
        tabs={[
          { id: 'detail', label: 'Detalle' },
          { id: 'related', label: 'Relacionados', count: related.length },
          { id: 'history', label: 'Historial', count: history.length },
        ]}
      />
      <TabPanel idPrefix="obj" id={tab} className={styles.body}>
        {tab === 'detail' && (
          <div className={styles.stack}>
            {alerts.map((a) => (
              <AlertCard key={a.id} alert={a} subject={target} onOpen={onOpen} />
            ))}
            <section className={styles.section}>
              <h3 className={styles.sectionTitle}>Datos</h3>
              <div className={styles.box}>
                <KeyValue items={view.detail(object, links)} labelWidth={168} />
              </div>
            </section>
          </div>
        )}
        {tab === 'related' &&
          (groups.length === 0 ? (
            <EmptyState size="sm" title="Sin objetos relacionados" description="Ningún otro objeto del paquete lo referencia." />
          ) : (
            <div className={styles.stack}>
              {groups.map((g) => {
                const v = viewOfObject(g.kind)
                return (
                  <section key={g.kind} className={styles.section}>
                    <h3 className={styles.sectionTitle}>
                      {v.label} <span className={styles.sectionCount}>{formatNumber(g.refs.length)}</span>
                    </h3>
                    <ul className={styles.related}>
                      {g.refs.map((r) => {
                        const o = links.get(r)!
                        const flagged = links.alertsOf(r).length > 0
                        return (
                          <li key={refKey(r)}>
                            <button type="button" className={styles.relatedCard} onClick={() => onOpen(r)}>
                              <v.icon aria-hidden className={styles.relatedIcon} />
                              <span className={styles.relatedText}>
                                <span className={styles.relatedTitle}>{v.title(o, links)}</span>
                                <Mono muted>{r.id}</Mono>
                              </span>
                              {flagged && <AlertTriangle aria-label="Con alertas" className={styles.flag} />}
                              <span className={styles.relatedAside}>{v.aside(o)}</span>
                              <ArrowRight aria-hidden className={styles.arrow} />
                            </button>
                          </li>
                        )
                      })}
                    </ul>
                  </section>
                )
              })}
            </div>
          ))}
        {tab === 'history' &&
          (history.length === 0 ? (
            <EmptyState size="sm" title="El ERP no registra cambios de este objeto" />
          ) : (
            <ol className={styles.timeline}>
              {history.map((e) => (
                <li key={e.id} className={styles.event}>
                  <span className={styles.dot} data-change={e.field ? true : undefined} aria-hidden />
                  <div className={styles.eventBody}>
                    <span className={styles.eventAction}>
                      {erpActionLabel(e.action)}
                      {e.field && (
                        <>
                          {' de '}
                          <Mono>{e.field}</Mono>
                        </>
                      )}
                    </span>
                    <span className={styles.eventMeta}>
                      {formatDateTime(e.at)} · {e.user ?? 'sin usuario'}
                    </span>
                    {(e.before != null || e.after != null) && (
                      <div className={styles.diff}>
                        <div>
                          <span className={styles.diffLabel}>Antes</span>
                          <Mono className={styles.before}>{e.before ?? '—'}</Mono>
                        </div>
                        <div>
                          <span className={styles.diffLabel}>Después</span>
                          <Mono>{e.after ?? '—'}</Mono>
                        </div>
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          ))}
      </TabPanel>
    </div>
  )
}
