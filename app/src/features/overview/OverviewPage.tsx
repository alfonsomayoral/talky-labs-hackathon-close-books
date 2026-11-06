// Resumen. Its question: what is left to close the period, and what needs a person?
// Title row with the finding, one strip per judging criterion, the alerts beside the bank reconciliation,
// the entities as cards and the package's contents as cards (ARCHITECTURE.md §5.2).
import { Link } from 'react-router'
import { ArrowRight, ChevronRight, FileWarning, Upload } from 'lucide-react'
import { Amount, Badge, ButtonLink, Button, EmptyState, Metric, Mono } from '@/components'
import type { Alert, Dataset, Run } from '@/domain'
import { ALERT_TYPE, MATCH_STATUS, SEVERITY, SEVERITY_ORDER, VIEWS, refKey, useData, type AnyObject, type Links } from '@/data'
import { EntityCard } from '@/features/entities/EntityCard'
import { ReconBar, ReconLegend } from '@/features/entities/ReconBar'
import { formatMonthLong, formatNumber, formatPercent } from '@/lib/format'
import { useEntityScope, useOpenObject, useScopedTo } from '@/lib/urlState'
import { matchCountsByEntity, sumCounts, type MatchCounts } from './model'
import styles from './Overview.module.css'

const ratio = (part: number, total: number) => (total > 0 ? part / total : null)
const pct = (v: number | null | undefined) => (v == null ? '—' : formatPercent(v))
const bySeverity = (a: Alert, b: Alert) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity)

function TitleRow({ dataset, run, alerts, counts, entity }: { dataset: Dataset; run: Run | null; alerts: Alert[]; counts: MatchCounts; entity: string | null }) {
  const [, open] = useOpenObject()
  const to = useScopedTo()
  const period = dataset.meta.period ?? run?.period ?? null
  const scope = entity ? dataset.entities.find((e) => e.id === entity)?.name : `${formatNumber(dataset.entities.length)} sociedades`
  const held = alerts.filter((a) => a.severity === 'high').length
  const pending = counts.suggested + counts.unmatched
  const first = [...alerts].sort(bySeverity)[0]
  return (
    <header className={styles.titleRow}>
      <div className={styles.titleText}>
        <h1 className={styles.title}>{period ? `Cierre de ${formatMonthLong(period)}` : 'Cierre del periodo'}</h1>
        <p className={styles.finding}>
          {run ? (
            <>
              <strong>
                {formatNumber(held)} {held === 1 ? 'operación retenida' : 'operaciones retenidas'} por riesgo
              </strong>{' '}
              y {formatNumber(pending)} {pending === 1 ? 'movimiento' : 'movimientos'} por revisar · {scope}
            </>
          ) : (
            <>El agente aún no ha ejecutado el cierre sobre estos datos · {scope}</>
          )}
        </p>
      </div>
      <div className={styles.actions}>
        <ButtonLink to={to('/importar')} leadingIcon={<Upload />}>
          Importar datos
        </ButtonLink>
        {first && (
          <Button variant="primary" onClick={() => open(refKey(first.subject))}>
            Revisar alertas
          </Button>
        )}
      </div>
    </header>
  )
}

/** One figure per judging criterion (PROBLEM.md §6), all read from the run. */
function Criteria({ run }: { run: Run | null }) {
  const m = run?.metrics
  const rec = m?.reconciliation
  const recTotal = rec ? rec.matched + rec.suggested + rec.unmatched : 0
  const autoTotal = m ? m.autonomy.auto + m.autonomy.review : 0
  const fraud = m ? Object.entries(m.fraud.byType).map(([t, n]) => `${n} ${ALERT_TYPE[t as Alert['type']].toLowerCase()}`) : []
  return (
    <section className={styles.criteria} aria-label="Criterios del jurado">
      <Metric label="Precisión contable" value={pct(m?.accuracy)} comparison={m?.accuracy == null ? 'Sin referencia con la que comparar' : 'Frente a la referencia'} hint="Asientos y saldos que deja el agente frente a los correctos." />
      <Metric label="Conciliación" value={pct(rec && ratio(rec.matched, recTotal))} comparison={rec ? `${formatNumber(rec.matched)} de ${formatNumber(recTotal)} movimientos casados` : 'Pendiente de ejecutar'} hint="Movimientos bancarios casados con el libro, sobre el total del periodo." />
      <Metric label="Detección de fraude" value={m ? formatNumber(m.fraud.detected) : '—'} comparison={m ? fraud.join(' · ') || 'Nada detectado' : 'Pendiente de ejecutar'} hint="Duplicados, errores fiscales y cambios bancarios sospechosos detectados." />
      <Metric label="Autonomía segura" value={pct(m && ratio(m.autonomy.auto, autoTotal))} comparison={m ? `${formatNumber(m.autonomy.review)} partidas a revisión humana` : 'Pendiente de ejecutar'} hint="Partidas que el agente resuelve solo; el resto queda en revisión con su motivo." />
      <Metric label="Auditabilidad" value={pct(m && ratio(m.auditability.withEvidence, m.auditability.total))} comparison={m ? `${formatNumber(m.auditability.withEvidence)} decisiones con evidencia` : 'Pendiente de ejecutar'} hint="Decisiones con su regla y los datos de origen que la prueban." />
    </section>
  )
}

function Alerts({ alerts, run }: { alerts: Alert[]; run: Run | null }) {
  const [, open] = useOpenObject()
  return (
    <section className={styles.card}>
      <header className={styles.cardHead}>
        <div>
          <h2 className={styles.cardTitle}>Te necesitan</h2>
          <p className={styles.cardSub}>{run ? 'Lo que el agente ha retenido o no ha podido cerrar solo' : 'Las alertas llegan con la ejecución del agente'}</p>
        </div>
        <span className={styles.cardCount}>{formatNumber(alerts.length)}</span>
      </header>
      {alerts.length === 0 ? (
        <EmptyState size="sm" title={run ? 'Nada pendiente de revisión' : 'Sin ejecución del agente'} />
      ) : (
        <ul className={styles.alerts}>
          {[...alerts].sort(bySeverity).map((a) => (
            <li key={a.id}>
              <button type="button" className={styles.alert} data-tone={SEVERITY[a.severity].tone} onClick={() => open(refKey(a.subject))}>
                <span className={styles.alertBody}>
                  <span className={styles.alertTitle}>{a.title}</span>
                  <span className={styles.alertReason}>{a.reason}</span>
                  <span className={styles.alertMeta}>
                    <Badge tone={SEVERITY[a.severity].tone}>{`${ALERT_TYPE[a.type]} · ${SEVERITY[a.severity].label}`}</Badge>
                    <Mono muted>{a.subject.id}</Mono>
                    <span>Sociedad {a.entityId}</span>
                  </span>
                </span>
                <span className={styles.alertAmount}>
                  <Amount cents={a.amountCents} currency={a.currency} />
                  <ChevronRight aria-hidden className={styles.chevron} />
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function Reconciliation({ dataset, byEntity, total, run, entity }: { dataset: Dataset; byEntity: Map<string, MatchCounts>; total: MatchCounts; run: Run | null; entity: string | null }) {
  const to = useScopedTo()
  const [, setEntity] = useEntityScope()
  const entities = entity ? dataset.entities.filter((e) => e.id === entity) : dataset.entities
  return (
    <section className={styles.card}>
      <header className={styles.cardHead}>
        <div>
          <h2 className={styles.cardTitle}>Conciliación bancaria</h2>
          <p className={styles.cardSub}>Movimientos del extracto frente al libro</p>
        </div>
      </header>
      <div className={styles.reconBody}>
        <div className={styles.reconFigure}>
          <span className={styles.bigFigure}>{run && total.total ? formatPercent(total.matched / total.total) : '—'}</span>
          <span className={styles.figureSub}>{run ? `${formatNumber(total.matched)} de ${formatNumber(total.total)} casados` : 'Pendiente de ejecutar'}</span>
        </div>
        <ReconBar counts={total} />
        <ReconLegend counts={total} />
        <Pending dataset={dataset} run={run} entity={entity} />
        <ul className={styles.entityBars}>
          {entities.map((e) => {
            const c = byEntity.get(e.id)!
            return (
              <li key={e.id}>
                <button type="button" className={styles.entityBar} onClick={() => setEntity(e.id)}>
                  <Mono muted>{e.id}</Mono>
                  <ReconBar counts={c} size="sm" />
                  <span className={styles.entityBarValue}>
                    {formatNumber(c.matched)}/{formatNumber(c.total)}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      </div>
      <footer className={styles.cardFoot}>
        <Link to={to('/banco')} className={styles.footLink}>
          Ver movimientos <ArrowRight aria-hidden />
        </Link>
      </footer>
    </section>
  )
}

/** The bank lines the agent could not match alone: suggested first, then unmatched. Opens each one. */
function Pending({ dataset, run, entity }: { dataset: Dataset; run: Run | null; entity: string | null }) {
  const [, open] = useOpenObject()
  const byId = new Map(dataset.bankTransactions.map((t) => [t.id, t]))
  const rows = (run?.matches ?? [])
    .filter((m) => m.status !== 'matched')
    .map((m) => ({ m, t: byId.get(m.bankTransactionId) }))
    .filter((x): x is { m: (typeof x)['m']; t: NonNullable<(typeof x)['t']> } => !!x.t && (!entity || x.t.entityId === entity))
    .sort((a, b) => Number(a.m.status === 'unmatched') - Number(b.m.status === 'unmatched'))
  if (!rows.length) return null
  return (
    <div className={styles.pending}>
      <span className={styles.pendingTitle}>Por revisar · {formatNumber(rows.length)}</span>
      {rows.slice(0, 3).map(({ m, t }) => (
        <button key={t.id} type="button" className={styles.pendingRow} onClick={() => open(refKey({ kind: 'bankTransaction', id: t.id }))}>
          <span className={styles.pendingText}>
            <Badge tone={MATCH_STATUS[m.status].tone} variant="outline" dot>
              {MATCH_STATUS[m.status].label}
            </Badge>
            <span className={styles.pendingLabel}>{t.counterparty ?? t.description}</span>
          </span>
          <Amount cents={t.amountCents} currency={t.currency} />
        </button>
      ))}
    </div>
  )
}

function DatasetCard({ view, rows, links, to }: { view: (typeof VIEWS)[number]; rows: AnyObject[]; links: Links; to: { pathname: string; search: string } | null }) {
  const body = (
    <>
      <div className={styles.preview} aria-hidden>
        {rows.slice(0, 3).map((o) => (
          <div key={o.id} className={styles.previewRow}>
            <span className={styles.previewTitle}>{view.title(o, links)}</span>
            <span className={styles.previewAside}>{view.aside(o)}</span>
          </div>
        ))}
        {rows.length === 0 && <div className={styles.previewEmpty}>Sin filas en el paquete</div>}
      </div>
      <div className={styles.dataText}>
        <div className={styles.dataHead}>
          <view.icon aria-hidden className={styles.dataIcon} />
          <span className={styles.dataLabel}>{view.label}</span>
          <span className={styles.dataCount}>{formatNumber(rows.length)}</span>
        </div>
        <p className={styles.dataDesc}>{to ? view.description : `${view.description} Se ven en cada objeto.`}</p>
      </div>
    </>
  )
  return to ? (
    <Link to={to} className={styles.dataCard}>
      {body}
    </Link>
  ) : (
    <div className={styles.dataCard} data-static>
      {body}
    </div>
  )
}

function Package({ dataset, entity }: { dataset: Dataset; entity: string | null }) {
  const to = useScopedTo()
  const links = useData((s) => s.links)!
  const problems = dataset.unmapped.length + dataset.issues.length
  return (
    <section className={styles.block}>
      <header className={styles.blockHead}>
        <div>
          <h2 className={styles.blockTitle}>Datos del cliente</h2>
          <p className={styles.cardSub}>Lo que contiene el paquete, por tipo. Cada tarjeta abre su tabla.</p>
        </div>
        {problems > 0 && (
          <Link to={to('/importar')} className={styles.warnLink}>
            <FileWarning aria-hidden /> {formatNumber(dataset.unmapped.length)} ficheros sin reconocer · {formatNumber(dataset.issues.length)} filas con problemas
          </Link>
        )}
      </header>
      <div className={styles.dataGrid}>
        {VIEWS.map((v) => {
          const rows = (dataset[v.kind] as AnyObject[]).filter((o) => !entity || (o.entityId ?? o.id) === entity)
          return <DatasetCard key={v.kind} view={v} rows={rows} links={links} to={v.path ? to(v.path) : null} />
        })}
      </div>
    </section>
  )
}

export function OverviewPage() {
  const dataset = useData((s) => s.dataset)!
  const run = useData((s) => s.run)
  const [entity, setEntity] = useEntityScope()
  const alerts = (run?.alerts ?? []).filter((a) => !entity || a.entityId === entity)
  const byEntity = matchCountsByEntity(dataset, run)
  const total = entity ? (byEntity.get(entity) ?? sumCounts([])) : sumCounts(byEntity.values())
  return (
    <div className={styles.page}>
      <TitleRow dataset={dataset} run={run} alerts={alerts} counts={total} entity={entity} />
      <div className={styles.stack}>
        <Criteria run={run} />
        {entity && <p className={styles.note}>Las cifras de arriba son de todo el grupo; el resto de la página, de la sociedad elegida.</p>}
      </div>
      <div className={styles.columns}>
        <Alerts alerts={alerts} run={run} />
        <Reconciliation dataset={dataset} byEntity={byEntity} total={total} run={run} entity={entity} />
      </div>
      {!entity && (
        <section className={styles.block}>
          <header className={styles.blockHead}>
            <div>
              <h2 className={styles.blockTitle}>Sociedades del grupo</h2>
              <p className={styles.cardSub}>Cada tarjeta filtra toda la aplicación por esa sociedad.</p>
            </div>
          </header>
          <div className={styles.entityGrid}>
            {dataset.entities.map((e) => (
              <EntityCard key={e.id} entity={e} dataset={dataset} run={run} counts={byEntity.get(e.id)!} onOpen={() => setEntity(e.id)} />
            ))}
          </div>
        </section>
      )}
      <Package dataset={dataset} entity={entity} />
    </div>
  )
}

