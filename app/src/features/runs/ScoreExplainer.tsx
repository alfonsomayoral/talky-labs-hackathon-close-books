import { Metric } from '@/components'
import type { OfficialResult, RunSummary, Score } from '@/domain'
import { formatDateTime, formatNumber, formatPercent } from '@/lib/format'
import { METRIC_LABEL, scoreReference } from './model'
import styles from './ScoreExplainer.module.css'

const WEIGHTED = ['allocation_f1', 'txn_accuracy', 'exception_macro_f1']

/** The score as the official scorer computes it, or what to compare with where the phase has no official answers. */
export function ScoreExplainer({ score, official, runs }: { score: Score | null; official: OfficialResult | null; runs: RunSummary[] }) {
  const reference = scoreReference(runs)
  const shown = score ?? official
  return (
    <div className={styles.explainer}>
      <p className={styles.formula}>Puntuación = 100 × (0,5 · F1 de pares + 0,3 · exactitud por movimiento + 0,2 · F1 macro de excepciones)</p>
      <p className={styles.note}>Un importe casa si difiere como mucho max(0,01; 0,5 %) del esperado.</p>
      {shown ? (
        <div className={styles.metrics}>
          <Metric
            label={score ? 'Puntuación' : 'Resultado oficial de la fase'}
            value={formatNumber(shown.score, { decimals: 2 })}
            comparison={official && !score ? formatDateTime(official.createdAt) : 'sobre 100'}
          />
          {WEIGHTED.filter((k) => shown.metrics[k] != null).map((k) => (
            <Metric key={k} label={METRIC_LABEL[k]} value={formatPercent(shown.metrics[k], { decimals: 1 })} />
          ))}
        </div>
      ) : (
        <p className={styles.note}>
          Esta fase no tiene respuestas oficiales: su puntuación solo se conoce al enviarla.
          {reference && ` Referencia, la ejecución abierta ${reference.runId}: ${formatNumber(reference.score, { decimals: 2 })}.`}
        </p>
      )}
    </div>
  )
}
