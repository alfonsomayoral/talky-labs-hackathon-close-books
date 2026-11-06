import clsx from 'clsx'
import { Mono, ProgressBar } from '@/components'
import { autoRate } from '@/domain'
import type { EntityStats } from '@/domain'
import { formatNumber, formatPercent } from '@/lib/format'
import styles from './EntityCard.module.css'

/** One company: pressing it scopes the whole app to it (and again to go back to the group). */
export function EntityCard({ stats, selected, onSelect }: { stats: EntityStats; selected: boolean; onSelect: () => void }) {
  const rate = autoRate(stats)
  return (
    <button type="button" className={clsx(styles.card, selected && styles.selected)} aria-pressed={selected} onClick={onSelect}>
      <span className={styles.head}>
        <Mono>{stats.entity}</Mono>
        <span className={styles.name}>{stats.name}</span>
      </span>
      <span className={styles.figures}>
        <span className={styles.rate}>{formatPercent(rate, { decimals: 0 })}</span>
        <span className={styles.meta}>
          {formatNumber(stats.txns)} mov. · {formatNumber(stats.reviewQueue)} en cola
        </span>
      </span>
      <ProgressBar value={rate ?? 0} size="sm" label={`${stats.name}: conciliado sin intervención`} />
    </button>
  )
}
