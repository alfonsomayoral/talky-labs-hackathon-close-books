import { ArrowRight } from 'lucide-react'
import { Amount, ButtonLink, Card, EmptyState, Metric, Mono, Page, PageHeader, Section, Skeleton } from '@/components'
import { useActiveRun, useQueueTotals, useRun, useRunStats } from '@/data'
import { autoRate, categoryLabel, queueOfKind, ruleDescription } from '@/domain'
import { formatDateTime, formatDate, formatMoney, formatNumber, formatPercent } from '@/lib/format'
import { useEntityScope, useScopedTo } from '@/lib/urlState'
import { DayChart } from './DayChart'
import { EntityCard } from './EntityCard'
import { KindCard } from './KindCard'
import { QueueCard } from './QueueCard'
import { EvidenceCard } from './EvidenceCard'
import { RankList } from './RankList'
import { ScoreSection } from './ScoreSection'
import { CategoryTerm, ExceptionTerm } from '@/features/shared'
import { amountSplit, closedExceptions, headline, modelTotals, periodMonths } from './model'
import styles from './OverviewPage.module.css'

const TOP = 8

export function OverviewPage() {
  const { runId, run } = useActiveRun()
  const [entity, setEntity] = useEntityScope()
  const scoped = useScopedTo()
  const statsQuery = useRunStats(runId, entity)
  const runQuery = useRun(runId)
  const totals = useQueueTotals(runId, entity)
  const stats = statsQuery.data
  const models = runQuery.data ? modelTotals(runQuery.data.models) : null

  const to = (pathname: string, params: Record<string, string> = {}) => {
    const link = scoped(pathname)
    const search = new URLSearchParams(link.search)
    for (const [key, value] of Object.entries(params)) search.set(key, value)
    return { pathname, search: `?${search}` }
  }

  if (statsQuery.error && !stats) {
    return (
      <Page>
        <PageHeader title="Resumen" />
        <EmptyState title="No se pudo cargar el resumen" description={statsQuery.error.message} />
      </Page>
    )
  }

  if (!stats) {
    return (
      <Page>
        <PageHeader title="Resumen" subtitle={<Skeleton width={280} />} />
        <div className={styles.metrics}>
          {[0, 1, 2, 3].map((i) => (
            <Card key={i}>
              <Metric label="" value="" loading />
            </Card>
          ))}
        </div>
        <Skeleton height={240} radius="var(--radius-lg)" />
      </Page>
    )
  }

  const scope = entity ? stats.byEntity.find((e) => e.entity === entity)?.name ?? entity : 'Todo el grupo'
  const split = amountSplit(stats)
  const biggestCategories = [...stats.byCategory].sort((a, b) => b.amountEur - a.amountEur).slice(0, 3).map((c) => categoryLabel(c.category)).join(', ')

  return (
    <Page>
      <div className={styles.banner} data-surface="feature">
        <PageHeader
          title={headline(stats, totals)}
          subtitle={[
            scope,
            `${formatDate(stats.periodFrom)} – ${formatDate(stats.periodTo)}`,
            ...(entity ? [] : [`${formatNumber(stats.byEntity.length)} sociedades`]),
            `${formatNumber(stats.txns)} movimientos`,
            ...(stats.periodFrom && stats.periodTo ? [`${formatNumber(periodMonths(stats.periodFrom, stats.periodTo))} meses`] : []),
          ].join(' · ')}
          actions={
            <ButtonLink variant="primary" to={to('/bandeja')} trailingIcon={<ArrowRight aria-hidden />}>
              Ver lo que te necesita
            </ButtonLink>
          }
        />
      </div>

      <div className={styles.queues}>
        <QueueCard label="Decidir" description="Varias opciones con la misma evidencia: decide una persona." totals={totals?.decidir} to={to('/bandeja', { vista: 'decidir' })} />
        <QueueCard label="Revisar" description="Sin evidencia para casar: cobros sin identificar, otras casaciones ambiguas y cargos." totals={totals?.revisar} to={to('/bandeja', { vista: 'revisar' })} />
        <QueueCard label="Reclamar" description="Ya conciliados, con algo que reclamar: parciales, disputas y clientes vencidos." totals={totals?.reclamar} to={to('/bandeja', { vista: 'reclamar' })} />
      </div>

      <div className={styles.metrics}>
        {run.officialResult && !entity && (
          <Card>
            <Metric
              label="Resultado oficial"
              value={formatNumber(run.officialResult.score, { decimals: 2 })}
              comparison={`sobre 100 · ${formatDateTime(run.officialResult.createdAt)}`}
              hint="Lo que respondió la clasificación del reto a esta ejecución."
            />
          </Card>
        )}
        <Card>
          <Metric
            label="Conciliado sin intervención"
            value={formatPercent(autoRate(stats), { decimals: 1 })}
            comparison={`${formatNumber(stats.txnsAuto)} de ${formatNumber(stats.txns)} movimientos`}
            hint="Movimientos sin ningún caso abierto para una persona."
          />
        </Card>
        <Card>
          <Metric
            label="Importe identificado"
            value={<Amount cents={stats.identifiedEur} compact />}
            comparison={
              split && (
                <>
                  {formatPercent(split.items, { decimals: 1 })} casado con partidas · {formatPercent(split.categories, { decimals: 0 })} categorías · {formatPercent(split.queue, { decimals: 1 })} en cola
                </>
              )
            }
            hint={`De ${formatMoney(stats.totalEur, 'EUR', { compact: true })} en movimientos. Identificado: los que tienen al menos una partida casada. Categorías: los que no liquidan ninguna${biggestCategories ? `, como ${biggestCategories}` : ''}.`}
          />
        </Card>
        <Card>
          <Metric
            label="Coste de modelo"
            value={models ? formatMoney(Math.round(models.costUsd * 100), 'USD', { decimals: 2 }) : ''}
            loading={!models}
            comparison={models ? `${formatNumber(models.calls)} llamadas; las reglas deciden` : undefined}
            hint="Los modelos solo extraen datos de PDFs y avisos de remesa; ninguna casación la elige un modelo."
          />
        </Card>
      </div>

      <Section title="Cómo se resolvió" description="Qué respalda cada movimiento: el sistema dice por qué casa algo y marca lo que no sabe.">
        <EvidenceCard byRule={stats.byRule} total={stats.txns} />
      </Section>

      <Section title="Evolución por día" description="Movimientos por fecha de contabilización, según se cerraron solos o pasaron a la cola.">
        <Card>{stats.byDay.length ? <DayChart byDay={stats.byDay} /> : <EmptyState size="sm" title="Sin movimientos en el periodo" />}</Card>
      </Section>

      <Section title="Casos por tipo" description="La misma cola, por tipo de caso. Cada tipo abre su pestaña de la bandeja." count={stats.byKind.length}>
        {stats.byKind.length ? (
          <div className={styles.kinds}>
            {stats.byKind.map((k) => (
              <KindCard key={k.kind} {...k} to={to('/bandeja', { vista: queueOfKind(k.kind), kind: k.kind })} />
            ))}
          </div>
        ) : (
          <EmptyState size="sm" title="No hay casos abiertos" description="Todo lo que había se cerró sin intervención." />
        )}
      </Section>

      <div className={styles.breakdowns}>
        <Section title="Excepciones" description="La lista cerrada de la política, por filas. Pasa el ratón para ver cada definición.">
          <Card padding="none">
            <RankList rows={closedExceptions(stats.byException).map((e) => ({ key: e.exception, label: <ExceptionTerm exception={e.exception} />, value: e.rows, detail: <Amount cents={e.amountEur} compact /> }))} />
          </Card>
        </Section>
        <Section title="Categorías" description="Movimientos sin factura, por categoría.">
          <Card padding="none">
            {stats.byCategory.length ? (
              <RankList rows={stats.byCategory.map((c) => ({ key: c.category, label: <CategoryTerm category={c.category} />, value: c.txns, detail: <Amount cents={c.amountEur} compact /> }))} />
            ) : (
              <EmptyState size="sm" title="Sin categorías" />
            )}
          </Card>
        </Section>
        <Section title="Filas por regla" description="Qué regla produjo cada fila. Abre la conciliación.">
          <Card padding="none">
            {stats.byRule.length ? (
              <RankList rows={stats.byRule.slice(0, TOP).map((r) => ({ key: r.rule, label: <Mono title={ruleDescription(r.rule)}>{r.rule}</Mono>, value: r.rows, to: to('/conciliacion', { regla: r.rule }) }))} />
            ) : (
              <EmptyState size="sm" title="Sin filas" />
            )}
          </Card>
        </Section>
      </div>

      <Section title="Por sociedad" description="Pulsa una para fijar el alcance de toda la plataforma." count={stats.byEntity.length}>
        <div className={styles.entities}>
          {stats.byEntity.map((e) => (
            <EntityCard key={e.entity} stats={e} selected={e.entity === entity} onSelect={() => setEntity(e.entity === entity ? null : e.entity)} />
          ))}
        </div>
      </Section>

      {stats.score && <ScoreSection score={stats.score} />}
    </Page>
  )
}
