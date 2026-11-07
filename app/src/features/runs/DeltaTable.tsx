import type { ReactNode } from 'react'
import clsx from 'clsx'
import { Badge } from '@/components'
import { isDrop, isRise, type Delta } from './model'
import styles from './DeltaTable.module.css'

export interface DeltaTableProps {
  /** Header of the first column. */
  head: string
  rows: Delta[]
  label: (row: Delta) => ReactNode
  format: (value: number, row: Delta) => string
  formatDelta: (value: number, row: Delta) => string
  /** A rise is good and a drop is bad (red row, «Baja»). Without it the difference is only a number. */
  judge?: boolean
  /** Header of the A and B columns. */
  a: string
  b: string
  caption: string
}

/** Two runs side by side with the difference: metrics, segments, rows per rule. */
export function DeltaTable({ head, rows, label, format, formatDelta, judge, a, b, caption }: DeltaTableProps) {
  const show = (v: number | null, r: Delta) => (v == null ? '—' : format(v, r))
  return (
    <table className={styles.table}>
      <caption className={styles.caption}>{caption}</caption>
      <thead>
        <tr>
          <th scope="col">{head}</th>
          <th scope="col">{a}</th>
          <th scope="col">{b}</th>
          <th scope="col">Diferencia</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const drop = judge && isDrop(r)
          const rise = judge && isRise(r)
          return (
            <tr key={r.key} className={clsx(drop && styles.drop)}>
              <th scope="row">{label(r)}</th>
              <td className="tabular">{show(r.a, r)}</td>
              <td className="tabular">{show(r.b, r)}</td>
              <td className={clsx('tabular', styles.delta, drop && styles.down, rise && styles.up)}>
                {r.delta == null ? '—' : r.delta === 0 ? '0' : formatDelta(r.delta, r)}
                {drop && (
                  <Badge tone="danger" className={styles.badge}>
                    Baja
                  </Badge>
                )}
                {rise && (
                  <Badge tone="ok" className={styles.badge}>
                    Sube
                  </Badge>
                )}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
