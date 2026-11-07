import { Link, type To } from 'react-router'
import { Amount, Skeleton } from '@/components'
import { formatNumber } from '@/lib/format'
import styles from './QueueCard.module.css'

interface QueueCardProps {
  label: string
  description: string
  totals?: { cases: number; amountEur: number }
  to: To
}

/** One kind of work a person has: opens its tab of the inbox. */
export function QueueCard({ label, description, totals, to }: QueueCardProps) {
  return (
    <Link to={to} className={styles.card} data-surface="feature">
      <span className={styles.label}>{label}</span>
      {totals ? (
        <span className={styles.figures}>
          <span className={styles.count}>{formatNumber(totals.cases)}</span>
          <Amount cents={totals.amountEur} compact />
        </span>
      ) : (
        <Skeleton width={120} height={32} />
      )}
      <span className={styles.description}>{description}</span>
    </Link>
  )
}
