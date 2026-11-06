import { Fragment, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { ArrowLeft, CloudOff } from 'lucide-react'
import type { BankLine, RelatedTxn, TxnDetail } from '@/domain'
import { CASE_STATUS_LABEL, CASE_STATUS_TONE } from '@/domain'
import { Amount, Badge, Button, ConfidenceBand, EmptyState, KeyValue, Mono, SidePanel, Skeleton } from '@/components'
import { useActiveRun, useTransaction } from '@/data'
import { formatDate, formatPercent } from '@/lib/format'
import { useScopedTo } from '@/lib/urlState'
import { TxnEvidence } from './TxnEvidence'
import { TxnRows } from './TxnRows'
import { decisionOf } from './txnPanelModel'
import styles from './TxnPanel.module.css'

export interface TxnPanelProps {
  bankTxnId: string
  onClose: () => void
}

const RELATION_LABEL: Record<string, string> = {
  returnOf: 'Devolución de',
  returnedBy: 'Devuelto por',
  duplicateOf: 'Duplicado de',
  representmentOf: 'Reintento de',
  sameBatch: 'Misma remesa',
}

const BANK_LINE_LABEL: Record<keyof BankLine, string> = {
  bankTxnId: 'Id del movimiento',
  accountId: 'Cuenta',
  entity: 'Sociedad',
  bank: 'Banco',
  statementFormat: 'Formato',
  statementFile: 'Extracto',
  bookingDate: 'Fecha contable',
  valueDate: 'Fecha valor',
  amountCents: 'Importe',
  currency: 'Divisa',
  bankCode: 'Código banco',
  bankSubcode: 'Subcódigo',
  ref1: 'Referencia 1',
  ref2: 'Referencia 2',
  text: 'Texto',
  counterpartyName: 'Contraparte',
  counterpartyAccount: 'Cuenta contraparte',
  endToEndId: 'End to end',
  remittanceInfo: 'Información de remesa',
  origAmountCents: 'Importe original',
  origCurrency: 'Divisa original',
}

/** Ids, accounts and codes; the rest (text, names, dates, amounts) is plain. */
const MONO_FIELDS = new Set<keyof BankLine>(['bankTxnId', 'accountId', 'entity', 'statementFormat', 'statementFile', 'bankCode', 'bankSubcode', 'ref1', 'ref2', 'counterpartyAccount', 'endToEndId', 'currency', 'origCurrency'])

const PARTY_KIND_LABEL = { customer: 'Cliente', supplier: 'Proveedor' }

function PanelSection({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <section className={styles.section}>
      <h3 className={styles.heading}>
        {title}
        {count != null && <span className={styles.count}>{count}</span>}
      </h3>
      {children}
    </section>
  )
}

function bankLineItems(txn: BankLine) {
  return (Object.keys(BANK_LINE_LABEL) as (keyof BankLine)[]).map((key) => {
    const value = txn[key]
    const text =
      key === 'amountCents' ? <Amount cents={txn.amountCents} currency={txn.currency} signed /> : key === 'origAmountCents' && txn.origAmountCents != null ? <Amount cents={txn.origAmountCents} currency={txn.origCurrency ?? txn.currency} /> : key === 'bookingDate' || key === 'valueDate' ? formatDate(txn[key]) : value
    return { label: BANK_LINE_LABEL[key], value: text, mono: MONO_FIELDS.has(key) }
  })
}

function Related({ items, onOpen }: { items: RelatedTxn[]; onOpen: (id: string) => void }) {
  return (
    <ul className={styles.related}>
      {items.map((r) => (
        <li key={r.bankTxnId}>
          <button type="button" className={styles.relatedRow} onClick={() => onOpen(r.bankTxnId)}>
            <span className={styles.relation}>{RELATION_LABEL[r.relation] ?? r.relation}</span>
            <Mono>{r.bankTxnId}</Mono>
            <span className={styles.relatedText}>{r.text}</span>
            <span className={styles.relatedDate}>{formatDate(r.bookingDate)}</span>
            <Amount cents={r.amountCents} currency={r.currency} signed />
          </button>
        </li>
      ))}
    </ul>
  )
}

function Content({ detail, onOpen }: { detail: TxnDetail; onOpen: (id: string) => void }) {
  const { txn, rows, party, candidates, evidence, related } = detail
  const caseLink = useCaseLink(detail.case?.caseId)
  const decision = decisionOf(rows)
  return (
    <div className={styles.body}>
      <div className={styles.summary}>
        <div className={styles.amount}>
          <Amount cents={txn.amountCents} currency={txn.currency} signed />
        </div>
        <p className={styles.text}>{txn.text}</p>
        <p className={styles.meta}>
          {formatDate(txn.bookingDate)} · <Mono>{txn.entity}</Mono> · <Mono>{txn.accountId}</Mono>
        </p>
      </div>

      <PanelSection title="Decisión">
        <p className={styles.decision}>
          {decision.rules.length > 0 ? decision.rules.map((r, i) => (
            <Fragment key={r}>
              {i > 0 && ', '}
              <Mono>{r}</Mono>
            </Fragment>
          )) : 'Sin regla'}
          {decision.confidence != null && <> con confianza {formatPercent(decision.confidence, { decimals: 0 })}</>}
          {party ? <> sobre <strong>{party.partyName}</strong></> : ', sin tercero'}
        </p>
        <div className={styles.chips}>
          <ConfidenceBand value={decision.confidence} />
          {detail.case && <Badge tone={CASE_STATUS_TONE[detail.case.status]}>{CASE_STATUS_LABEL[detail.case.status]}</Badge>}
        </div>
        {detail.case && (
          <div className={styles.case}>
            <p>{detail.case.summary}</p>
            {caseLink && (
              <Link to={caseLink} className={styles.link}>
                Abrir el caso <Mono>{detail.case.caseId}</Mono>
              </Link>
            )}
          </div>
        )}
      </PanelSection>

      <PanelSection title="Partidas asignadas" count={rows.length}>
        {rows.length > 0 ? <TxnRows rows={rows} /> : <p className={styles.none}>Ninguna fila para este movimiento.</p>}
      </PanelSection>

      <PanelSection title="Evidencia" count={evidence.length}>
        {evidence.length > 0 ? (
          <div className={styles.stack}>
            {evidence.map((e) => (
              <TxnEvidence key={`${e.kind}:${e.ref}`} evidence={e} onOpenTxn={onOpen} />
            ))}
          </div>
        ) : (
          <p className={styles.none}>La regla no cita ninguna fuente además del movimiento.</p>
        )}
      </PanelSection>

      <PanelSection title="Tercero">
        {party ? (
          <KeyValue
            labelWidth={120}
            items={[
              { label: 'Nombre', value: party.partyName },
              { label: 'Id', value: party.partyId, mono: true },
              { label: 'Tipo', value: PARTY_KIND_LABEL[party.partyKind] },
              { label: 'Ordenante', value: party.payerName },
              { label: 'Cómo se resolvió', value: party.how, mono: true },
              { label: 'Confianza', value: <ConfidenceBand value={party.confidence} showValue /> },
              ...party.alternatives.map((a, i) => ({
                label: i === 0 ? 'Alternativas' : '',
                value: (
                  <span className={styles.alt}>
                    {a.partyName} <Mono muted>{a.partyId}</Mono> {formatPercent(a.score, { decimals: 0 })}
                  </span>
                ),
              })),
            ]}
          />
        ) : (
          <p className={styles.none}>No se pudo resolver ningún tercero.</p>
        )}
        {candidates.length > 0 && (
          <div className={styles.candidates}>
            <h4 className={styles.subheading}>Candidatos descartados</h4>
            <ul className={styles.candidateList}>
              {candidates.map((c) => (
                <li key={c.itemId} className={styles.candidate}>
                  <Mono>{c.itemId}</Mono>
                  <Amount cents={c.amountCents} currency={c.currency} />
                  <span className={styles.why}>{c.why}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </PanelSection>

      <PanelSection title="El movimiento en el banco">
        <KeyValue labelWidth={150} items={bankLineItems(txn)} />
        {related.length > 0 && (
          <div className={styles.candidates}>
            <h4 className={styles.subheading}>Movimientos relacionados</h4>
            <Related items={related} onOpen={onOpen} />
          </div>
        )}
      </PanelSection>
    </div>
  )
}

function useCaseLink(caseId: string | undefined) {
  const scoped = useScopedTo()('/bandeja')
  if (!caseId) return null
  const search = new URLSearchParams(scoped.search)
  search.set('ver', caseId)
  return { pathname: scoped.pathname, search: `?${search}` }
}

/** Side panel of one bank movement: what it settles and why, with the evidence open. */
export function TxnPanel({ bankTxnId, onClose }: TxnPanelProps) {
  const { runId } = useActiveRun()
  // A related movement opens in place, with a way back; a new `bankTxnId` from the parent resets it.
  const [opened, setOpened] = useState<{ from: string; id: string } | null>(null)
  const id = opened?.from === bankTxnId ? opened.id : bankTxnId
  const q = useTransaction(runId, id)

  return (
    <SidePanel
      open
      onClose={onClose}
      defaultWidth={720}
      minWidth={520}
      storageKey="txn-panel-width"
      aria-label="Detalle del movimiento"
      title={
        <span className={styles.title}>
          {opened?.from === bankTxnId && (
            <Button variant="ghost" size="sm" leadingIcon={<ArrowLeft />} onClick={() => setOpened(null)}>
              Volver
            </Button>
          )}
          Movimiento <Mono>{id}</Mono>
        </span>
      }
    >
      {q.data ? (
        <Content detail={q.data} onOpen={(next) => setOpened({ from: bankTxnId, id: next })} />
      ) : q.error ? (
        <EmptyState icon={<CloudOff />} title="No se pudo cargar el movimiento" description={q.error.message} />
      ) : (
        <div className={styles.body}>
          <Skeleton height={64} />
          <Skeleton height={120} />
          <Skeleton height={200} />
        </div>
      )}
    </SidePanel>
  )
}
