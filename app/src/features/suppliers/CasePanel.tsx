import { useMemo, useRef } from 'react'
import { ArrowUpRight, CircleAlert } from 'lucide-react'
import { Amount, Badge, ButtonLink, EmptyState, KeyValue, Mono, SidePanel, Skeleton } from '@/components'
import { useCase, useOpenItems } from '@/data'
import { caseStatusBadge, PRIORITY_LABEL, caseKindLabel } from '@/domain'
import { formatDate, formatNumber } from '@/lib/format'
import { useScopedTo } from '@/lib/urlState'
import { CaseActions } from '@/features/shared'
import { orderItems } from './model'
import styles from './CasePanel.module.css'

interface CasePanelProps {
  runId: string
  /** `?ver=` of the page: the open case, or null. */
  caseId: string | null
  onClose: () => void
}

/** The supplier incident open on the right: what is wrong, the items involved and the email to send. */
export function CasePanel({ runId, caseId, onClose }: CasePanelProps) {
  // The panel slides out after `caseId` is gone: keep showing the case it had.
  const shown = useRef(caseId)
  if (caseId) shown.current = caseId
  const { data: c, isPending, error } = useCase(runId, shown.current)
  const scoped = useScopedTo()

  const movement = (bankTxnId: string) => {
    const to = scoped('/conciliacion')
    const search = new URLSearchParams(to.search)
    search.set('ver', bankTxnId)
    return { pathname: to.pathname, search: `?${search}` }
  }

  return (
    <SidePanel
      open={caseId != null}
      onClose={onClose}
      title={c ? caseKindLabel(c.kind) : 'Incidencia'}
      storageKey="suppliers-panel-width"
      aria-label="Detalle de la incidencia"
      actions={
        c?.bankTxnId ? (
          <ButtonLink to={movement(c.bankTxnId)} variant="ghost" size="sm" trailingIcon={<ArrowUpRight />}>
            Ver movimiento
          </ButtonLink>
        ) : undefined
      }
    >
      {error ? (
        <EmptyState size="sm" icon={<CircleAlert />} title="No se ha podido abrir la incidencia" description={error.message} />
      ) : isPending || !c ? (
        <div className={styles.body} aria-busy>
          <Skeleton height={20} width="60%" />
          <Skeleton lines={3} />
          <Skeleton height={120} />
        </div>
      ) : (
        <div className={styles.body}>
          <p className={styles.summary}>{c.summary}</p>
          <KeyValue
            className={styles.facts}
            labelWidth={110}
            items={[
              { label: 'Estado', value: <Badge emphasis={caseStatusBadge(c).emphasis}>{caseStatusBadge(c).label}</Badge> },
              { label: 'Prioridad', value: PRIORITY_LABEL[c.priority] },
              { label: 'Importe', value: <Amount cents={c.amountCents} currency={c.currency} /> },
              ...(c.currency !== 'EUR' ? [{ label: 'En euros', value: <Amount cents={c.amountEur} currency="EUR" /> }] : []),
              { label: 'Proveedor', value: c.partyName },
              { label: 'Sociedad', value: c.entity, mono: true },
              { label: 'Movimiento', value: c.bookingDate ? formatDate(c.bookingDate) : null },
              { label: 'Caso', value: c.caseId, mono: true },
            ]}
          />
          <Items runId={runId} partyId={c.partyId} entity={c.entity} caseItemIds={c.itemIds} />
          <CaseActions caseDetail={c} runId={runId} onResolved={onClose} />
        </div>
      )}
    </SidePanel>
  )
}

const ITEM_KIND: Record<string, string> = { API: 'Factura', APC: 'Abono', ARI: 'Factura', ARC: 'Abono' }

/** Open items of the supplier, those of the case first and marked. */
function Items({ runId, partyId, entity, caseItemIds }: { runId: string; partyId: string | null; entity: string; caseItemIds: string[] }) {
  const items = useOpenItems(runId, partyId ? { partyId, entity } : { partyId: '-' })
  const ordered = useMemo(() => orderItems(items.rows, caseItemIds), [items.rows, caseItemIds])

  if (items.error) return <EmptyState size="sm" icon={<CircleAlert />} title="No se han podido cargar las partidas" description={items.error.message} />
  if (items.loading) return <Skeleton height={108} />
  if (ordered.length === 0) return <p className={styles.note}>Sin partidas abiertas de este proveedor.</p>

  return (
    <section aria-labelledby="supplier-items">
      <h3 id="supplier-items" className={styles.heading}>
        Partidas del proveedor
        {items.total != null && <span className={styles.count}> · {formatNumber(items.total)}</span>}
      </h3>
      <div className={styles.table}>
        <div className={styles.head} aria-hidden>
          <span>Documento</span>
          <span>Tipo</span>
          <span>Vence</span>
          <span className={styles.right}>Importe</span>
          <span />
        </div>
        <ul className={styles.items}>
          {ordered.map(({ item, inCase }) => (
            <li key={item.itemId} className={styles.item} data-in-case={inCase || undefined}>
              <Mono>{item.documentNumber}</Mono>
              <span className={styles.kindCell}>{ITEM_KIND[item.itemType] ?? item.itemType}</span>
              <span className={styles.due}>{item.dueDate ? formatDate(item.dueDate) : '—'}</span>
              <Amount cents={item.totalCents} currency={item.currency} />
              <span className={styles.flag}>{inCase && <Badge emphasis="medium">Del caso</Badge>}</span>
            </li>
          ))}
        </ul>
      </div>
      {items.rows.length < (items.total ?? 0) && (
        <p className={styles.note}>Se muestran {formatNumber(items.rows.length)} partidas; las del caso van primero si están entre ellas.</p>
      )}
    </section>
  )
}
