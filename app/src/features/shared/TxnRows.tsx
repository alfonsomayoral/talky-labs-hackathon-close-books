import type { DetailRow } from '@/domain'
import { exceptionLabel } from '@/domain'
import { Amount, Badge, Mono } from '@/components'
import { formatDate } from '@/lib/format'
import { sumByCurrency } from './txnPanelModel'
import styles from './TxnRows.module.css'

/** The rows of the movement: up to ~1.5 k, so the box has a fixed height and scrolls. */
export function TxnRows({ rows }: { rows: DetailRow[] }) {
  const totals = sumByCurrency(rows)
  return (
    <div className={styles.box}>
      <div className={styles.scroll} role="table" aria-label="Partidas asignadas">
        <div className={styles.head} role="row">
          <span role="columnheader">Número</span>
          <span role="columnheader">Tercero</span>
          <span role="columnheader">Vence</span>
          <span role="columnheader" className={styles.num}>
            Total
          </span>
          <span role="columnheader" className={styles.num}>
            Aplicado
          </span>
          <span role="columnheader">Excepción</span>
        </div>
        {rows.map((r, i) => (
          <div key={`${r.itemId ?? 'sin'}-${i}`} className={styles.row} role="row">
            <span role="cell">{r.item ? <Mono>{r.item.documentNumber}</Mono> : <span className={styles.muted}>Sin partida</span>}</span>
            <span role="cell" className={styles.party} title={r.item?.partyName}>
              {r.item?.partyName ?? '—'}
            </span>
            <span role="cell" className={styles.date}>
              {formatDate(r.item?.dueDate)}
            </span>
            <span role="cell" className={styles.num}>
              {r.item ? <Amount cents={r.item.totalCents} currency={r.item.currency} /> : '—'}
            </span>
            <span role="cell" className={styles.num}>
              <Amount cents={r.amountCents} currency={r.currency ?? 'EUR'} />
            </span>
            <span role="cell">
              {r.exception ? (
                <Badge tone={r.exception === 'UNIDENTIFIED' ? 'danger' : 'warn'}>{exceptionLabel(r.exception)}</Badge>
              ) : r.category ? (
                <Mono>{r.category}</Mono>
              ) : null}
            </span>
          </div>
        ))}
      </div>
      <footer className={styles.footer}>
        <span>{rows.length === 1 ? '1 fila' : `${rows.length} filas`}</span>
        <span className={styles.totals}>
          {totals.map((t) => (
            <span key={t.currency}>
              Aplicado <Amount cents={t.cents} currency={t.currency} />
            </span>
          ))}
        </span>
      </footer>
    </div>
  )
}
