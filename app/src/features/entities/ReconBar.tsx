// Bank matches as one stacked bar: casadas in the brand green (the screen's data hue), sugeridas in its pale tint,
// sin casar in grey. The legend is the same marks scaled down.
import { formatNumber } from '@/lib/format'
import type { MatchCounts } from '@/features/overview/model'
import styles from './ReconBar.module.css'

const PARTS = [
  { key: 'matched', label: 'Casadas' },
  { key: 'suggested', label: 'Sugeridas' },
  { key: 'unmatched', label: 'Sin casar' },
] as const

export function ReconBar({ counts, size = 'md' }: { counts: MatchCounts; size?: 'sm' | 'md' }) {
  const label = PARTS.map((p) => `${p.label}: ${counts[p.key]}`).join(', ')
  return (
    <div className={styles.bar} data-size={size} role="img" aria-label={counts.total ? label : 'Sin movimientos'}>
      {counts.total > 0 &&
        PARTS.map((p) => (counts[p.key] > 0 ? <span key={p.key} className={styles.part} data-part={p.key} style={{ flexGrow: counts[p.key] }} /> : null))}
    </div>
  )
}

export function ReconLegend({ counts }: { counts: MatchCounts }) {
  return (
    <ul className={styles.legend}>
      {PARTS.map((p) => (
        <li key={p.key}>
          <span className={styles.swatch} data-part={p.key} aria-hidden />
          <span className={styles.legendLabel}>{p.label}</span>
          <span className={styles.legendValue}>{formatNumber(counts[p.key])}</span>
        </li>
      ))}
    </ul>
  )
}
