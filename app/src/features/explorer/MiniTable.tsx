import type { ReactNode } from 'react'
import { Link, type To } from 'react-router'
import clsx from 'clsx'
import styles from './MiniTable.module.css'

export interface MiniColumn<T> {
  header: string
  cell: (row: T) => ReactNode
  width?: string
  align?: 'right'
}

interface MiniTableProps<T> {
  rows: T[]
  columns: MiniColumn<T>[]
  getKey: (row: T) => string
  /** Makes every row a link. */
  rowTo?: (row: T) => To
  'aria-label': string
}

/** Compact list for a side panel: the few rows of one object (a DataTable would be too much for 200 rows). */
export function MiniTable<T>({ rows, columns, getKey, rowTo, ...aria }: MiniTableProps<T>) {
  const grid = { ['--mt-cols' as string]: columns.map((c) => c.width ?? 'minmax(0, 1fr)').join(' ') }
  return (
    <div className={styles.table} role="table" style={grid} {...aria}>
      <div className={clsx(styles.row, styles.header)} role="row">
        {columns.map((c) => (
          <span key={c.header} role="columnheader" className={clsx(c.align === 'right' && styles.right)}>
            {c.header}
          </span>
        ))}
      </div>
      <div className={styles.body}>
        {rows.map((row) => {
          const cells = columns.map((c) => (
            <span key={c.header} role="cell" className={clsx(styles.cell, c.align === 'right' && styles.right)}>
              {c.cell(row)}
            </span>
          ))
          return rowTo ? (
            <Link key={getKey(row)} to={rowTo(row)} className={clsx(styles.row, styles.link)} role="row">
              {cells}
            </Link>
          ) : (
            <div key={getKey(row)} className={styles.row} role="row">
              {cells}
            </div>
          )
        })}
      </div>
    </div>
  )
}
