import { useId, useMemo, type ReactNode } from 'react'
import { ArrowRight, GitCompare } from 'lucide-react'
import { Badge, Card, EmptyState, Mono, Skeleton } from '@/components'
import { useRun, useRuns } from '@/data'
import type { Run, RunSummary } from '@/domain'
import { formatNumber, formatPercent } from '@/lib/format'
import { useTextParam } from '@/lib/urlState'
import { DeltaTable } from './DeltaTable'
import { METRIC_LABEL, defaultPair, diffCounts, diffMetrics, diffSegments, isDrop, type Delta } from './model'
import styles from './CompareTab.module.css'

const signed = (format: (v: number) => string) => (v: number) => (v > 0 ? `+${format(v)}` : format(v))
const points = (v: number) => formatPercent(v, { decimals: 1 })
const count = (v: number) => formatNumber(v)

function RunSelect({ label, value, runs, onChange }: { label: string; value: string | null; runs: RunSummary[]; onChange: (id: string) => void }) {
  const id = useId()
  return (
    <div className={styles.field}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      <select id={id} className={styles.select} value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
        {value == null && <option value="">Elige una ejecución</option>}
        {runs.map((r) => (
          <option key={r.runId} value={r.runId}>
            {r.runId} · {r.phase}
            {r.score != null ? ` · ${formatNumber(r.score, { decimals: 2 })}` : ''}
          </option>
        ))}
      </select>
    </div>
  )
}

function Result({ a, b }: { a: Run; b: Run }) {
  const scored = a.score != null && b.score != null
  const metrics = useMemo<Delta[]>(() => {
    if (!a.score || !b.score) return []
    const total = { key: 'total', a: a.score.score, b: b.score.score, delta: b.score.score - a.score.score }
    return [total, ...diffMetrics(a.score, b.score)]
  }, [a.score, b.score])
  const segments = useMemo(() => (a.score && b.score ? diffSegments(a.score, b.score) : []), [a.score, b.score])
  const rules = useMemo(() => diffCounts(a.byRule, b.byRule), [a.byRule, b.byRule])
  const changed = rules.filter((r) => r.delta !== 0)
  const drops = segments.filter(isDrop).length

  return (
    <>
      {scored ? (
        <>
          <Card title="Puntuación" description="Diferencia entre la ejecución nueva y la base." padding="none">
            <DeltaTable
              caption="Puntuación y métricas"
              head="Métrica"
              a="Base"
              b="Nueva"
              rows={metrics}
              label={(r) => (r.key === 'total' ? <strong>Total</strong> : METRIC_LABEL[r.key])}
              format={(v, r) => (r.key === 'total' ? formatNumber(v, { decimals: 2 }) : points(v))}
              formatDelta={(v, r) => signed(r.key === 'total' ? (x) => formatNumber(x, { decimals: 2 }) : points)(v)}
              judge
            />
          </Card>
          <Card
            title="Segmentos"
            description="Acierto por tipo de movimiento. Los que bajan van primero."
            actions={drops > 0 ? <Badge tone="danger">{drops === 1 ? '1 segmento baja' : `${drops} segmentos bajan`}</Badge> : <Badge tone="ok">Ninguno baja</Badge>}
            padding="none"
          >
            <DeltaTable
              caption="Acierto por segmento"
              head="Segmento"
              a="Base"
              b="Nueva"
              rows={segments}
              label={(r) => (
                <span className={styles.segment}>
                  <Mono>{r.key}</Mono>
                  {r.n != null && <span className={styles.n}>{formatNumber(r.n)} mov.</span>}
                </span>
              )}
              format={points}
              formatDelta={signed(points)}
              judge
            />
          </Card>
        </>
      ) : (
        <Card>
          <EmptyState
            size="sm"
            icon={<GitCompare />}
            title="Una de las dos no tiene puntuación"
            description="Solo se puntúan las fases con respuestas, como TRAIN y holdout. Abajo se comparan igualmente las filas por regla."
          />
        </Card>
      )}
      <Card
        title="Filas por regla"
        description={`${changed.length === 1 ? 'Cambia 1 regla' : `Cambian ${changed.length} reglas`}${rules.length > changed.length ? `; ${rules.length - changed.length} quedan igual` : ''}.`}
        padding="none"
      >
        {changed.length === 0 ? (
          <EmptyState size="sm" title="Las dos ejecuciones producen las mismas filas por regla" />
        ) : (
          <DeltaTable caption="Filas por regla" head="Regla" a="Base" b="Nueva" rows={changed} label={(r) => <Mono>{r.key}</Mono>} format={count} formatDelta={signed(count)} />
        )}
      </Card>
    </>
  )
}

/** Two runs side by side: did the score move, which segments dropped, which rules took the rows. */
export function CompareTab() {
  const runs = useRuns()
  const [pa, setA] = useTextParam('a')
  const [pb, setB] = useTextParam('b')
  const pair = useMemo(() => defaultPair(runs.data ?? []), [runs.data])
  const aId = pa ?? pair.a
  const bId = pb ?? pair.b
  const a = useRun(aId)
  const b = useRun(bId)

  if (runs.isPending) return <Skeleton height={240} />
  if (runs.error) return <EmptyState title="No se ha podido cargar el historial" description={runs.error.message} />
  if (runs.data.length < 2) {
    return <EmptyState icon={<GitCompare />} title="Hacen falta dos ejecuciones para comparar" description="Lanza otra desde la consola y vuelve aquí." />
  }

  let body: ReactNode
  if (!aId || !bId) body = <EmptyState size="sm" title="Elige las dos ejecuciones" />
  else if (aId === bId) body = <EmptyState size="sm" title="Has elegido la misma ejecución dos veces" description="Cambia una de las dos para ver las diferencias." />
  else if (a.error || b.error) body = <EmptyState size="sm" title="No se ha podido cargar una de las ejecuciones" description={(a.error ?? b.error)?.message} />
  else if (!a.data || !b.data) body = <Skeleton height={240} />
  else body = <Result a={a.data} b={b.data} />

  return (
    <div className={styles.tab}>
      <div className={styles.pickers}>
        <RunSelect label="Base" value={aId} runs={runs.data} onChange={setA} />
        <ArrowRight className={styles.arrow} aria-hidden />
        <RunSelect label="Nueva" value={bId} runs={runs.data} onChange={setB} />
      </div>
      {body}
    </div>
  )
}
