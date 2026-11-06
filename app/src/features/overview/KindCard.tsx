import { Link, type To } from 'react-router'
import { Amount } from '@/components'
import { caseKindLabel } from '@/domain'
import { formatNumber } from '@/lib/format'
import styles from './KindCard.module.css'

/** A type of case in the queue: opens the inbox filtered by it. */
export function KindCard({ kind, cases, amountEur, to }: { kind: string; cases: number; amountEur: number; to: To }) {
  return (
    <Link to={to} className={styles.card}>
      <span className={styles.label}>{caseKindLabel(kind)}</span>
      <span className={styles.count}>{formatNumber(cases)}</span>
      <span className={styles.amount}>
        <Amount cents={amountEur} compact />
      </span>
    </Link>
  )
}
