import type { DocumentFact, Evidence } from '@/domain'
import { Amount, Badge, KeyValue, Mono } from '@/components'
import styles from './TxnEvidence.module.css'

const KIND_LABEL: Record<string, string> = {
  remittanceAdvice: 'Aviso de remesa',
  directDebitBatch: 'Remesa de adeudos',
  cardSettlement: 'Liquidación de tarjetas',
  chequeDeposit: 'Remesa de cheques',
  paymentRun: 'Pago masivo',
  pdf: 'PDF',
  customer: 'Cliente (maestro)',
  supplier: 'Proveedor (maestro)',
  bankAccount: 'Cuenta bancaria (maestro)',
  fxRate: 'Tipo de cambio',
  bankLine: 'Otro movimiento',
  memoryRule: 'Regla de memoria',
  humanDecision: 'Decisión de una persona',
}

function Facts({ facts }: { facts: DocumentFact[] }) {
  return (
    <div className={styles.scroll}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Factura</th>
            <th className={styles.num}>Bruto</th>
            <th className={styles.num}>Deducción</th>
            <th>Motivo</th>
            <th className={styles.num}>Pagado</th>
            <th>Extraído por</th>
          </tr>
        </thead>
        <tbody>
          {facts.map((f, i) => (
            <tr key={i}>
              <td>
                <Mono>{f.documentNumber ?? '—'}</Mono>
              </td>
              <td className={styles.num}>
                <Amount cents={f.grossCents} currency={f.currency ?? 'EUR'} />
              </td>
              <td className={styles.num}>
                <Amount cents={f.deductionCents} currency={f.currency ?? 'EUR'} />
              </td>
              <td>{f.reason ?? '—'}</td>
              <td className={styles.num}>
                <Amount cents={f.paidCents} currency={f.currency ?? 'EUR'} />
              </td>
              <td>
                <Badge variant="outline" tone={f.method === 'model' ? 'info' : 'neutral'} title={f.model ?? undefined}>
                  {f.method === 'model' ? 'Modelo' : 'Parser'}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Content({ evidence }: { evidence: Evidence }) {
  const c = evidence.content
  switch (c.type) {
    case 'document':
      return (
        <>
          {c.text && <pre className={styles.text}>{c.text}</pre>}
          {c.facts.length > 0 && <Facts facts={c.facts} />}
        </>
      )
    case 'detailFile':
      return (
        <div className={styles.scroll}>
          <table className={styles.table}>
            <thead>
              <tr>
                {c.columns.map((col) => (
                  <th key={col}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {c.rows.map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j}>
                      <Mono>{cell}</Mono>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    case 'record':
      return <KeyValue labelWidth={110} items={Object.entries(c.fields).map(([label, value]) => ({ label, value: value == null ? '—' : String(value) }))} />
    case 'none':
      return null
  }
}

/** One source of the decision, with its content opened in line. */
export function TxnEvidence({ evidence, onOpenTxn }: { evidence: Evidence; onOpenTxn: (bankTxnId: string) => void }) {
  return (
    <article className={styles.evidence}>
      <header className={styles.header}>
        <Badge variant="outline">{KIND_LABEL[evidence.kind] ?? evidence.kind}</Badge>
        {evidence.kind === 'bankLine' ? (
          <button type="button" className={styles.open} onClick={() => onOpenTxn(evidence.ref)}>
            <Mono>{evidence.ref}</Mono>
          </button>
        ) : (
          <Mono className={styles.ref} title={evidence.ref}>
            {evidence.label ?? evidence.ref}
          </Mono>
        )}
      </header>
      <Content evidence={evidence} />
    </article>
  )
}
