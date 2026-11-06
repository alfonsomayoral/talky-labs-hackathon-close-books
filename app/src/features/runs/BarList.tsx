import type { ReactNode } from 'react'
import { ProgressBar } from '@/components'
import { formatNumber } from '@/lib/format'
import styles from './BarList.module.css'

export interface BarItem {
  key: string
  label: ReactNode
  value: number
  /** Text for the number column; defaults to the formatted value. */
  display?: string
}

/** Rows of name, bar relative to the biggest, and number: stages, rows per rule, per exception. */
export function BarList({ items, label }: { items: BarItem[]; label: string }) {
  const max = Math.max(1, ...items.map((i) => i.value))
  return (
    <ul className={styles.list} aria-label={label}>
      {items.map((i) => (
        <li key={i.key} className={styles.row}>
          <span className={styles.name}>{i.label}</span>
          <ProgressBar size="sm" value={i.value} max={max} label={`${i.key}: ${i.display ?? formatNumber(i.value)}`} />
          <span className={`${styles.value} tabular`}>{i.display ?? formatNumber(i.value)}</span>
        </li>
      ))}
    </ul>
  )
}
