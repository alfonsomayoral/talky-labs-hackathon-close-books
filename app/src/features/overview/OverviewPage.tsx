import { ArrowRight } from 'lucide-react'
import { Amount, ButtonLink, Card, EmptyState, Metric, Mono, Page, PageHeader, Section, Skeleton } from '@/components'
import { useActiveRun, useRun, useRunStats } from '@/data'
import { autoRate, exceptionLabel } from '@/domain'
import { formatDate, formatMoney, formatNumber, formatPercent } from '@/lib/format'
import { useEntityScope, useScopedTo } from '@/lib/urlState'
import { DayChart } from './DayChart'
import { EntityCard } from './EntityCard'
import { KindCard } from './KindCard'
import { RankList } from './RankList'
import { ScoreSection } from './ScoreSection'
import { headline, identifiedShare, modelTotals } from './model'
import styles from './OverviewPage.module.css'

const TOP = 8

export function OverviewPage() {
  const { runId } = useActiveRun()
  const [entity, setEntity] = useEntityScope()
  const scoped = useScopedTo()
  const statsQuery = useRunStats(runId, entity)
  const runQuery = useRun(runId)
  const stats = statsQuery.data
  const models = runQuery.data ? modelTotals(runQuery.data.models) : null

  const to = (pathname: string, param?: [string, string]) => {
    const link = scoped(pathname)
    if (!param) return link
    const search = new URLSearchParams(link.search)
    search.set(...param)
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
  const share = identifiedShare(stats)

  return (
    <Page>
      <PageHeader
        title={headline(stats)}
        subtitle={`${scope} · fase ${stats.phase} · ${formatDate(stats.periodFrom)} – ${formatDate(stats.periodTo)}`}
        actions={
          <ButtonLink variant="primary" to={to('/bandeja')} trailingIcon={<ArrowRight aria-hidden />}>
            Ver lo que te necesita
          </ButtonLink>
        }
      />

      <div className={styles.metrics}>
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
              <>
                {formatPercent(share, { decimals: 1 })} de <Amount cents={stats.totalEur} compact />
              </>
            }
            hint="Suma del importe en euros de los movimientos con al menos una partida casada."
          />
        </Card>
        <Card>
          <Metric
            label="Cola de revisión"
            value={formatNumber(stats.reviewQueue)}
            comparison={
              <>
                casos · <Amount cents={stats.reviewQueueEur} compact />
              </>
            }
            hint="Casos por revisar, con pregunta o sin casación."
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

      <Section title="Evolución por día" description="Movimientos por fecha de contabilización, según se cerraron solos o pasaron a la cola.">
        <Card>{stats.byDay.length ? <DayChart byDay={stats.byDay} /> : <EmptyState size="sm" title="Sin movimientos en el periodo" />}</Card>
      </Section>

      <Section title="Casos por tipo" description="Lo que espera a una persona. Cada tipo abre la bandeja filtrada." count={stats.byKind.length}>
        {stats.byKind.length ? (
          <div className={styles.kinds}>
            {stats.byKind.map((k) => (
              <KindCard key={k.kind} {...k} to={to('/bandeja', ['kind', k.kind])} />
            ))}
          </div>
        ) : (
          <EmptyState size="sm" title="No hay casos abiertos" description="Todo lo que había se cerró sin intervención." />
        )}
      </Section>

      <div className={styles.breakdowns}>
        <Section title="Excepciones" description="Partidas por tipo de diferencia.">
          <Card padding="none">
            {stats.byException.length ? (
              <RankList
                rows={stats.byException.slice(0, TOP).map((e) => ({ key: e.exception, label: exceptionLabel(e.exception), value: e.rows, detail: <Amount cents={e.amountEur} compact /> }))}
              />
            ) : (
              <EmptyState size="sm" title="Sin excepciones" />
            )}
          </Card>
        </Section>
        <Section title="Categorías" description="Movimientos sin factura, por categoría.">
          <Card padding="none">
            {stats.byCategory.length ? (
              <RankList rows={stats.byCategory.slice(0, TOP).map((c) => ({ key: c.category, label: <Mono>{c.category}</Mono>, value: c.txns, detail: <Amount cents={c.amountEur} compact /> }))} />
            ) : (
              <EmptyState size="sm" title="Sin categorías" />
            )}
          </Card>
        </Section>
        <Section title="Filas por regla" description="Qué regla produjo cada fila. Abre la conciliación.">
          <Card padding="none">
            {stats.byRule.length ? (
              <RankList rows={stats.byRule.slice(0, TOP).map((r) => ({ key: r.rule, label: <Mono>{r.rule}</Mono>, value: r.rows, to: to('/conciliacion', ['regla', r.rule]) }))} />
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
