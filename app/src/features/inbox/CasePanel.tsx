import { useRef } from 'react'
import { ArrowUpRight, CircleAlert } from 'lucide-react'
import { Amount, Badge, ButtonLink, EmptyState, KeyValue, Mono, SidePanel, Skeleton } from '@/components'
import { useCase } from '@/data'
import { CASE_STATUS_LABEL, CASE_STATUS_TONE, PRIORITY_LABEL, caseKindLabel, ruleDescription } from '@/domain'
import { formatDate } from '@/lib/format'
import { useScopedTo } from '@/lib/urlState'
import { CaseActions } from '@/features/shared'
import styles from './CasePanel.module.css'

interface CasePanelProps {
  runId: string
  /** `?ver=` of the page: the open case, or null. */
  caseId: string | null
  onClose: () => void
}

/** The case open on the right: what happened and the one thing to do about it. */
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
      title={c ? caseKindLabel(c.kind) : 'Caso'}
      storageKey="inbox-panel-width"
      aria-label="Detalle del caso"
      actions={
        c?.bankTxnId ? (
          <ButtonLink to={movement(c.bankTxnId)} variant="ghost" size="sm" trailingIcon={<ArrowUpRight />}>
            Ver movimiento
          </ButtonLink>
        ) : undefined
      }
    >
      {error ? (
        <EmptyState size="sm" icon={<CircleAlert />} title="No se ha podido abrir el caso" description={error.message} />
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
            labelWidth={110}
            items={[
              { label: 'Estado', value: <Badge tone={CASE_STATUS_TONE[c.status]}>{CASE_STATUS_LABEL[c.status]}</Badge> },
              { label: 'Prioridad', value: PRIORITY_LABEL[c.priority] },
              { label: 'Importe', value: <Amount cents={c.amountCents} currency={c.currency} /> },
              ...(c.currency !== 'EUR' ? [{ label: 'En euros', value: <Amount cents={c.amountEur} currency="EUR" /> }] : []),
              { label: 'Tercero', value: c.partyName },
              { label: 'Sociedad', value: c.entity, mono: true },
              { label: 'Movimiento', value: c.bookingDate ? formatDate(c.bookingDate) : null },
              { label: 'Regla', value: c.rule ? <Mono title={ruleDescription(c.rule)}>{c.rule}</Mono> : null },
              { label: 'Caso', value: c.caseId, mono: true },
            ]}
          />
          <CaseActions caseDetail={c} runId={runId} onResolved={onClose} />
        </div>
      )}
    </SidePanel>
  )
}
