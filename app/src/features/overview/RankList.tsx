import type { ReactNode } from 'react'
import { Link, type To } from 'react-router'
import { formatNumber } from '@/lib/format'
import styles from './RankList.module.css'

export interface RankRow {
  key: string
  label: ReactNode
  /** Main figure, the one the bar draws. */
  value: number
  /** Second figure on the right (an amount). */
  detail?: ReactNode
  to?: To
}

/** Rows with a thin bar proportional to the biggest one; a row with `to` is a link. */
export function RankList({ rows, total }: { rows: RankRow[]; total?: number }) {
  const max = total ?? Math.max(1, ...rows.map((r) => r.value))
  return (
    <ul className={styles.list}>
      {rows.map((r) => {
        const body = (
          <>
            <span className={styles.label}>{r.label}</span>
            <span className={styles.value}>{formatNumber(r.value)}</span>
            <span className={styles.detail}>{r.detail}</span>
            <span className={styles.bar} style={{ width: `${(r.value / max) * 100}%` }} aria-hidden />
          </>
        )
        return (
          <li key={r.key}>
            {r.to ? (
              <Link to={r.to} className={styles.row}>
                {body}
              </Link>
            ) : (
              <div className={styles.row}>{body}</div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
