import { AlertTriangle } from 'lucide-react'
import { Amount, Badge, Mono } from '@/components'
import { ALERT_TYPE, OBJECT_LABEL, SEVERITY, refKey } from '@/data'
import type { Alert, ObjectRef } from '@/domain'
import styles from './ObjectPanel.module.css'

/** One alert of the run with its reason, rule, evidence and what the person has to do. */
export function AlertCard({ alert, subject, onOpen }: { alert: Alert; subject: ObjectRef; onOpen: (r: ObjectRef) => void }) {
  const sev = SEVERITY[alert.severity]
  const others = [alert.subject, ...alert.evidence].filter((r) => refKey(r) !== refKey(subject))
  return (
    <section className={styles.alert} data-tone={sev.tone}>
      <header className={styles.alertHead}>
        <AlertTriangle aria-hidden className={styles.alertIcon} />
        <span className={styles.alertTitle}>{alert.title}</span>
        <Amount cents={alert.amountCents} currency={alert.currency} />
      </header>
      <p className={styles.alertReason}>{alert.reason}</p>
      <p className={styles.alertAction}>
        <strong>Qué hacer:</strong> {alert.action}
      </p>
      <footer className={styles.alertFoot}>
        <Badge tone={sev.tone}>{`${ALERT_TYPE[alert.type]} · ${sev.label}`}</Badge>
        <Mono muted>{alert.rule}</Mono>
        {others.map((r) => (
          <button key={refKey(r)} type="button" className={styles.evidence} onClick={() => onOpen(r)}>
            {OBJECT_LABEL[r.kind]} <Mono>{r.id}</Mono>
          </button>
        ))}
      </footer>
    </section>
  )
}
