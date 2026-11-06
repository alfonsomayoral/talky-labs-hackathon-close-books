// Resumen: where the close stands, one tile per judging criterion, what needs a person,
// the group's entities and what the package contains (ARCHITECTURE.md §5.2).
import { Link } from 'react-router'
import { AlertTriangle, ArrowRight, FileWarning } from 'lucide-react'
import { Amount, Badge, Card, EmptyState, Metric, Mono, Page, Section } from '@/components'
import type { Alert, Dataset, Run } from '@/domain'
import { ALERT_TYPE, PAGE_VIEWS, SEVERITY, SEVERITY_ORDER, refKey, useData } from '@/data'
import { formatMonth, formatNumber, formatPercent } from '@/lib/format'
import { useEntityScope, useOpenObject, useScopedTo } from '@/lib/urlState'
import styles from './Overview.module.css'

const ratio = (part: number, total: number) => (total > 0 ? part / total : null)

function Opener({ dataset, run, entity }: { dataset: Dataset; run: Run | null; entity: string | null }) {
  const period = dataset.meta.period ?? run?.period ?? null
  const holding = dataset.entities.find((e) => !e.parentId)
  const scopeName = entity ? (dataset.entities.find((e) => e.id === entity)?.name ?? entity) : (holding?.name ?? dataset.meta.name)
  const r = run?.metrics.reconciliation
  const total = r ? r.matched + r.suggested + r.unmatched : 0
  const held = run?.alerts.filter((a) => a.severity === 'high').length ?? 0
  return (
    <header className={styles.hero}>
      <p className={styles.dateLine}>
        {period ? `Cierre de ${formatMonth(period)}` : 'Periodo por determinar'} · {scopeName}
        {!entity && ` · ${formatNumber(dataset.entities.length)} sociedades`}
      </p>
      {run && r ? (
        <h1 className={styles.headline}>
          El agente ha conciliado <span className={styles.headlineKey}>{formatNumber(r.matched)}</span> de {formatNumber(total)} movimientos y retiene{' '}
          <span className={styles.headlineKey}>{formatNumber(held)}</span> {held === 1 ? 'operación de riesgo' : 'operaciones de riesgo'}.
        </h1>
      ) : (
        <h1 className={styles.headline}>
          Datos cargados. <span className={styles.headlineKey}>El cierre está pendiente de ejecutar.</span>
        </h1>
      )}
      <p className={styles.runLine}>
        <Badge variant="outline">{dataset.meta.source === 'fixtures' ? 'Datos de muestra' : 'Paquete importado'}</Badge>
        <span>{dataset.meta.name}</span>
        {run ? (
          <>
            <Mono muted>{run.id}</Mono>
            <span>Agente {run.agent.version}</span>
          </>
        ) : (
          <span>Sin ejecución del agente</span>
        )}
      </p>
    </header>
  )
}

/** One tile per judging criterion (PROBLEM.md §6). The figures come from the run, never computed here. */
function Criteria({ run }: { run: Run | null }) {
  const m = run?.metrics
  const rec = m?.reconciliation
  const recTotal = rec ? rec.matched + rec.suggested + rec.unmatched : 0
  const autoTotal = m ? m.autonomy.auto + m.autonomy.review : 0
  const pct = (v: number | null | undefined) => (v == null ? '—' : formatPercent(v))
  return (
    <div className={styles.vitals}>
      <Metric label="Precisión contable" value={pct(m?.accuracy)} comparison={m?.accuracy == null ? 'Sin referencia con la que comparar' : 'frente a la referencia'} hint="Asientos y saldos que deja el agente frente a los correctos." />
      <Metric
        label="Conciliación"
        value={pct(rec && ratio(rec.matched, recTotal))}
        comparison={rec ? `${formatNumber(rec.matched)} casadas · ${formatNumber(rec.suggested)} sugeridas · ${formatNumber(rec.unmatched)} sin casar` : 'Pendiente de ejecutar'}
        hint="Movimientos bancarios casados con el libro, sobre el total del periodo."
      />
      <Metric
        label="Detección de fraude"
        value={m ? formatNumber(m.fraud.detected) : '—'}
        comparison={m ? Object.entries(m.fraud.byType).map(([t, n]) => `${n} ${ALERT_TYPE[t as Alert['type']].toLowerCase()}`).join(' · ') || 'Nada detectado' : 'Pendiente de ejecutar'}
        hint="Duplicados, errores fiscales y cambios bancarios sospechosos detectados."
      />
      <Metric
        label="Autonomía segura"
        value={pct(m && ratio(m.autonomy.auto, autoTotal))}
        comparison={m ? `${formatNumber(m.autonomy.auto)} solas · ${formatNumber(m.autonomy.review)} a revisión` : 'Pendiente de ejecutar'}
        hint="Partidas que el agente resuelve solo; el resto queda en revisión humana con su motivo."
      />
      <Metric
        label="Auditabilidad"
        value={pct(m && ratio(m.auditability.withEvidence, m.auditability.total))}
        comparison={m ? `${formatNumber(m.auditability.withEvidence)} de ${formatNumber(m.auditability.total)} decisiones con evidencia` : 'Pendiente de ejecutar'}
        hint="Decisiones con su regla y los datos de origen que la prueban."
      />
    </div>
  )
}

function NeedsYou({ alerts }: { alerts: Alert[] }) {
  const [, open] = useOpenObject()
  const sorted = [...alerts].sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity))
  return (
    <Card title="Te necesitan" description={`${formatNumber(alerts.length)} ${alerts.length === 1 ? 'alerta' : 'alertas'} del agente`} padding="none">
      {sorted.length === 0 ? (
        <EmptyState size="sm" title="Nada pendiente de revisión" />
      ) : (
        <ul className={styles.alerts}>
          {sorted.map((a) => (
            <li key={a.id}>
              <button type="button" className={styles.alertRow} onClick={() => open(refKey(a.subject))}>
                <AlertTriangle aria-hidden className={styles.alertIcon} data-tone={SEVERITY[a.severity].tone} />
                <span className={styles.alertText}>
                  <span className={styles.alertTitle}>{a.title}</span>
                  <span className={styles.alertSub}>
                    {ALERT_TYPE[a.type]} · <Mono muted>{a.subject.id}</Mono> · {a.entityId}
                  </span>
                </span>
                <Amount cents={a.amountCents} currency={a.currency} compact />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function Entities({ dataset, run }: { dataset: Dataset; run: Run | null }) {
  const [, setEntity] = useEntityScope()
  return (
    <Card title="Sociedades del grupo" padding="none">
      <ul className={styles.entities}>
        {dataset.entities.map((e) => {
          const alerts = run?.alerts.filter((a) => a.entityId === e.id).length ?? 0
          return (
            <li key={e.id}>
              <button type="button" className={styles.entityRow} onClick={() => setEntity(e.id)}>
                <Mono muted>{e.id}</Mono>
                <span className={styles.entityName}>
                  {e.name}
                  <span className={styles.entityMeta}>
                    {e.country} · {e.currency} · {formatNumber(dataset.invoices.filter((i) => i.entityId === e.id).length)} facturas ·{' '}
                    {formatNumber(dataset.bankTransactions.filter((t) => t.entityId === e.id).length)} movimientos
                  </span>
                </span>
                {alerts > 0 ? <Badge tone="warn">{`${alerts} ${alerts === 1 ? 'alerta' : 'alertas'}`}</Badge> : <Badge tone="ok">Sin alertas</Badge>}
              </button>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}

function Inventory({ dataset, entity }: { dataset: Dataset; entity: string | null }) {
  const to = useScopedTo()
  const count = (rows: { entityId?: string; id: string }[]) => (entity ? rows.filter((r) => (r.entityId ?? r.id) === entity).length : rows.length)
  const problems = dataset.unmapped.length + dataset.issues.length
  return (
    <Section title="Datos del paquete" description="Lo que contiene el paquete del cliente, por tipo." actions={problems > 0 ? <Link to={to('/importar')} className={styles.warnLink}><FileWarning aria-hidden /> {formatNumber(dataset.unmapped.length)} ficheros sin reconocer · {formatNumber(dataset.issues.length)} filas con problemas</Link> : undefined}>
      <ul className={styles.inventory}>
        {PAGE_VIEWS.map((v) => (
          <li key={v.kind}>
            <Link to={to(v.path!)} className={styles.tile}>
              <v.icon aria-hidden className={styles.tileIcon} />
              <span className={styles.tileLabel}>{v.label}</span>
              <span className={styles.tileCount}>{formatNumber(count(dataset[v.kind] as { entityId?: string; id: string }[]))}</span>
              <ArrowRight aria-hidden className={styles.tileArrow} />
            </Link>
          </li>
        ))}
        <li>
          <div className={styles.tile}>
            <span className={styles.tileLabel}>Eventos del historial del ERP</span>
            <span className={styles.tileCount}>{formatNumber(count(dataset.erpEvents))}</span>
          </div>
        </li>
      </ul>
    </Section>
  )
}

export function OverviewPage() {
  const dataset = useData((s) => s.dataset)!
  const run = useData((s) => s.run)
  const [entity] = useEntityScope()
  const alerts = (run?.alerts ?? []).filter((a) => !entity || a.entityId === entity)
  return (
    <Page>
      <div className={styles.page}>
        <Opener dataset={dataset} run={run} entity={entity} />
        <div className={styles.criteria}>
          <Criteria run={run} />
          {entity && <p className={styles.note}>Las métricas del agente son de todo el grupo; las alertas y los datos, de la sociedad elegida.</p>}
        </div>
        <div className={styles.columns}>
          <NeedsYou alerts={alerts} />
          <Entities dataset={dataset} run={run} />
        </div>
        <Inventory dataset={dataset} entity={entity} />
      </div>
    </Page>
  )
}
