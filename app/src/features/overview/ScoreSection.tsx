import { Card, Metric, ProgressBar, Section } from '@/components'
import { segmentLabel, type Score } from '@/domain'
import { formatNumber, formatPercent } from '@/lib/format'
import { scoreMetrics, segmentsWorstFirst } from './model'
import styles from './ScoreSection.module.css'

/** Local score against the golden (only phases that have one): total, its three parts, and the segments from worst to best. */
export function ScoreSection({ score }: { score: Score }) {
  return (
    <Section title="Puntuación contra las respuestas de la fase" description="Evaluador oficial; los tipos de movimiento van del peor al mejor.">
      <div className={styles.grid}>
        <Card>
          <div className={styles.metrics}>
            <Metric size="lg" label="Puntuación total" value={formatNumber(score.score, { decimals: 1 })} comparison="sobre 100" />
            {scoreMetrics(score).map((m) => (
              <Metric key={m.key} label={m.label} value={formatPercent(m.value, { decimals: 1 })} comparison={`peso ${formatPercent(m.weight)}`} />
            ))}
          </div>
        </Card>
        <Card padding="none">
          <ul className={styles.segments}>
            {segmentsWorstFirst(score).map((s) => (
              <li key={s.key} className={styles.segment}>
                <span title={s.key}>{segmentLabel(s.key)}</span>
                <span className={styles.n}>{formatNumber(s.n)} mov.</span>
                <ProgressBar value={s.accuracy} size="sm" tone={s.accuracy < 0.7 ? 'warn' : 'brand'} label={`${segmentLabel(s.key)}: acierto`} />
                <span className={styles.accuracy}>{formatPercent(s.accuracy, { decimals: 1 })}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </Section>
  )
}
