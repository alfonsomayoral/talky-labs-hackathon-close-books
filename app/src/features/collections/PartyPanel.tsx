import { useMemo, useRef } from 'react'
import { CircleAlert } from 'lucide-react'
import { Amount, Badge, DataTable, EmptyState, KeyValue, Mono, Section, SidePanel, Skeleton, type Column } from '@/components'
import { useCase, useOpenItems, useParty } from '@/data'
import { CASE_STATUS_LABEL, CASE_STATUS_EMPHASIS, caseKindLabel, type AgingParty, type CaseRow, type OpenItem } from '@/domain'
import { formatDate, formatNumber } from '@/lib/format'
import { Link } from 'react-router'
import { useScopedTo } from '@/lib/urlState'
import { CaseActions } from '@/features/shared'
import { AgingBar } from './AgingBar'
import { RISK_HEURISTIC, RISK_LABEL, RISK_EMPHASIS, riskOf } from './model'
import styles from './PartyPanel.module.css'

interface PartyPanelProps {
  runId: string
  /** `?ver=` of the page: the open customer, or null. */
  partyId: string | null
  /** The list's rows: they carry the overdue-balance case of each customer. */
  aging: AgingParty[]
  onClose: () => void
}

const ITEM_ROW = 44
const ITEMS_MAX_HEIGHT = 8 * ITEM_ROW + 40
const RECENT_MOVEMENTS = 8
const OWN_CASE_KINDS = ['dispute', 'duplicate_payment']

const itemColumns: Column<OpenItem>[] = [
  { id: 'documentNumber', header: 'Factura', width: 'minmax(110px, 1.2fr)', cell: (i) => <Mono>{i.documentNumber}</Mono> },
  { id: 'dueDate', header: 'Vence', width: 96, cell: (i) => <span className="tabular">{formatDate(i.dueDate)}</span> },
  { id: 'daysOverdue', header: 'Días', width: 72, align: 'right', cell: (i) => <span className="tabular">{formatNumber(i.daysOverdue)}</span> },
  { id: 'open', header: 'Abierto', width: 120, align: 'right', cell: (i) => <Amount cents={i.openAtEndCents} currency={i.currency} /> },
]

/** The customer open on the right: who they owe us as, what is open and the email to chase it. */
export function PartyPanel({ runId, partyId, aging, onClose }: PartyPanelProps) {
  // The panel slides out after `partyId` is gone: keep showing the customer it had.
  const shown = useRef(partyId)
  if (partyId) shown.current = partyId
  const id = shown.current

  const { data: detail, isPending, error } = useParty(runId, id)
  const items = useOpenItems(runId, id ? { partyId: id, overdue: true } : {})
  const row = aging.find((p) => p.partyId === id)
  const scoped = useScopedTo()

  // The list only carries the top 200: for any other customer, look for the case among their own.
  const chaseCaseId = row?.caseId ?? detail?.cases.find((c) => c.kind === 'overdue_customer')?.caseId ?? null
  const chaseCase = useCase(runId, chaseCaseId)

  const own = useMemo(() => (detail?.cases ?? []).filter((c) => OWN_CASE_KINDS.includes(c.kind)), [detail])
  const recent = useMemo(
    () => [...(detail?.transactions ?? [])].sort((a, b) => b.bookingDate.localeCompare(a.bookingDate)).slice(0, RECENT_MOVEMENTS),
    [detail],
  )

  const movement = (bankTxnId: string) => {
    const to = scoped('/conciliacion')
    const search = new URLSearchParams(to.search)
    search.set('ver', bankTxnId)
    return { pathname: to.pathname, search: `?${search}` }
  }

  const party = detail?.party
  const parent = party?.parentId ? detail?.group.find((g) => g.partyId === party.parentId) : null
  const risk = row ? riskOf(row) : null

  return (
    <SidePanel open={partyId != null} onClose={onClose} title={party?.name ?? row?.partyName ?? 'Cliente'} storageKey="collections-panel-width" aria-label="Detalle del cliente">
      {error ? (
        <EmptyState size="sm" icon={<CircleAlert />} title="No se ha podido abrir el cliente" description={error.message} />
      ) : isPending || !party ? (
        <div className={styles.body} aria-busy>
          <Skeleton height={20} width="60%" />
          <Skeleton lines={4} />
          <Skeleton height={120} />
        </div>
      ) : (
        <div className={styles.body}>
          {row && (
            <div className={styles.summary}>
              <div className={styles.figures}>
                <Amount cents={row.overdueEur} currency="EUR" className={styles.big} />
                <span className={styles.muted}>vencido de </span>
                <Amount cents={row.openEur} currency="EUR" />
              </div>
              <AgingBar buckets={row.buckets} label="Saldo del cliente por tramo de vencimiento" size="md" />
              {risk && (
                <p className={styles.risk}>
                  <Badge emphasis={RISK_EMPHASIS[risk]}>Riesgo {RISK_LABEL[risk].toLowerCase()}</Badge>
                  <span>{RISK_HEURISTIC}</span>
                </p>
              )}
            </div>
          )}

          <KeyValue
            className={styles.facts}
            labelWidth={120}
            items={[
              { label: 'Id', value: party.partyId, mono: true },
              { label: 'Sociedad', value: party.entity, mono: true },
              { label: 'NIF', value: party.taxId, mono: true },
              { label: 'País', value: party.country },
              { label: 'Condiciones', value: party.paymentTerms },
              { label: 'Divisa', value: party.currency },
              { label: 'Grupo', value: detail.group.length > 0 ? `${detail.group.length + 1} sociedades${party.groupId ? ` (${party.groupId})` : ''}` : null },
              { label: 'Matriz', value: parent ? `${parent.name} (${parent.entity})` : null },
              { label: 'Bloqueado desde', value: party.blockedSince ? formatDate(party.blockedSince) : null },
            ].filter((item) => item.value != null)}
          />

          <Section title="Reclamar">
            {chaseCase.data ? (
              <CaseActions caseDetail={chaseCase.data} runId={runId} />
            ) : chaseCaseId ? (
              <Skeleton height={80} />
            ) : (
              <p className={styles.muted}>Este cliente no tiene un caso de cobro abierto, así que no hay correo que preparar desde aquí.</p>
            )}
          </Section>

          <Section title="Partidas vencidas" count={items.total ?? undefined}>
            {items.error ? (
              <EmptyState size="sm" icon={<CircleAlert />} title="No se han podido cargar las partidas" description={items.error.message} />
            ) : items.loading ? (
              <Skeleton height={ITEM_ROW * 3} />
            ) : (
              <DataTable
                aria-label="Partidas vencidas"
                rows={items.rows}
                columns={itemColumns}
                getRowId={(i) => i.itemId}
                onEndReached={items.loadMore}
                height={Math.min(Math.max(items.rows.length, 1) * ITEM_ROW + 40, ITEMS_MAX_HEIGHT)}
                empty={<EmptyState size="sm" title="Sin partidas vencidas" />}
              />
            )}
          </Section>

          <Section title="Disputas y duplicados" count={own.length}>
            {own.length === 0 ? <p className={styles.muted}>Ninguno abierto con este cliente.</p> : <ul className={styles.list}>{own.map((c) => <CaseLine key={c.caseId} c={c} />)}</ul>}
          </Section>

          <Section title="Últimos movimientos">
            {recent.length === 0 ? (
              <p className={styles.muted}>Sin movimientos asociados a este cliente.</p>
            ) : (
              <ul className={styles.list}>
                {recent.map((t) => (
                  <li key={t.bankTxnId}>
                    <Link to={movement(t.bankTxnId)} className={styles.movement}>
                      <span className={`${styles.date} tabular`}>{formatDate(t.bookingDate)}</span>
                      <span className={styles.truncate}>{t.text}</span>
                      <Amount cents={t.amountCents} currency={t.currency} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>
      )}
    </SidePanel>
  )
}

function CaseLine({ c }: { c: CaseRow }) {
  return (
    <li className={styles.case}>
      <div className={styles.caseHead}>
        <span className={styles.kind}>{caseKindLabel(c.kind)}</span>
        <Badge emphasis={CASE_STATUS_EMPHASIS[c.status]}>{CASE_STATUS_LABEL[c.status]}</Badge>
        <Amount cents={c.amountCents} currency={c.currency} className={styles.end} />
      </div>
      <p className={styles.caseSummary}>{c.summary}</p>
    </li>
  )
}
