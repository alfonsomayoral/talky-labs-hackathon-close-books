import type { BankLine, DetailRow } from '@/domain'
import { Amount, Mono } from '@/components'
import { formatDate } from '@/lib/format'
import { CategoryTerm, ExceptionTerm } from './Terms'
import { sumByCurrency } from './txnPanelModel'
import styles from './TxnRows.module.css'

/** The rows of the movement: up to ~1.5 k, so the box has a fixed height and scrolls. */
export function TxnRows({ rows, txn }: { rows: DetailRow[]; txn: Pick<BankLine, 'amountCents' | 'currency'> }) {
  const totals = sumByCurrency(rows)
  const otherCurrency = totals.some((t) => t.currency !== txn.currency)
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
            <span role="cell" className={styles.party} title={r.item?.partyName ?? undefined}>
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
                <ExceptionTerm exception={r.exception} badge />
              ) : r.category ? (
                <CategoryTerm category={r.category} />
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
          {otherCurrency && (
            <span>
              Movimiento <Amount cents={Math.abs(txn.amountCents)} currency={txn.currency} />
            </span>
          )}
        </span>
      </footer>
    </div>
  )
}
