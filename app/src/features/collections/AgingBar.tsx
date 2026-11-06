import { Amount, ProgressBar, toneColor, type ProgressSegment, type Tone } from '@/components'
import { AGING_BUCKETS, AGING_LABEL, type AgingBucket } from '@/domain'
import styles from './AgingBar.module.css'

const BUCKET_TONE: Record<AgingBucket, Tone> = { not_due: 'neutral', d1_30: 'info', d31_60: 'warn', d61_90: 'danger', d90_plus: 'danger' }

/** Stacked bar of the aging buckets (EUR cents). The bar reads euros so its tooltips do not show raw cents. */
export function AgingBar({ buckets, label, size = 'sm' }: { buckets: Record<AgingBucket, number>; label: string; size?: 'sm' | 'md' }) {
  const segments: ProgressSegment[] = AGING_BUCKETS.map((b) => ({ value: Math.round(buckets[b] / 100), tone: BUCKET_TONE[b], label: AGING_LABEL[b] }))
  return <ProgressBar segments={segments} size={size} label={label} />
}

/** Names the bar's segments, each with its amount. */
export function AgingLegend({ buckets }: { buckets: Record<AgingBucket, number> }) {
  return (
    <ul className={styles.legend}>
      {AGING_BUCKETS.map((b) => (
        <li key={b} className={styles.item}>
          <span className={styles.key} style={{ background: toneColor(BUCKET_TONE[b]) }} aria-hidden />
          <span>{AGING_LABEL[b]}</span>
          <Amount cents={buckets[b]} currency="EUR" compact />
        </li>
      ))}
    </ul>
  )
}
