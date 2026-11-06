import { useState } from 'react'
import { Check } from 'lucide-react'
import { Badge, Button, toast } from '@/components'
import { useDecideCase } from '@/data'
import type { CaseDetail } from '@/domain'
import { primaryAction } from './model'
import { DraftEditor } from './DraftEditor'
import { QuestionForm } from './QuestionForm'
import { TextField } from './TextField'
import styles from './CaseActions.module.css'

interface CaseActionsProps {
  caseDetail: CaseDetail
  runId: string
  /** The case left the queue: the screen can close its panel. */
  onResolved?: () => void
}

/** What a person can do with a case: the action that leads it (answer, email) and, always, marking it handled. */
export function CaseActions({ caseDetail, runId, onResolved }: CaseActionsProps) {
  const lead = primaryAction(caseDetail)
  const [note, setNote] = useState('')
  const decide = useDecideCase(runId)

  if (lead === 'closed') {
    return (
      <p className={styles.closed}>
        <Badge tone="neutral" icon={<Check />}>
          Gestionado
        </Badge>
      </p>
    )
  }

  const markDone = () =>
    decide.mutate(
      { caseId: caseDetail.caseId, action: 'done', note },
      {
        onSuccess: () => {
          toast.success('Caso marcado como gestionado')
          onResolved?.()
        },
        onError: (error) => toast.error('No se ha podido marcar el caso', { description: error.message }),
      },
    )

  return (
    <div className={styles.actions}>
      {lead === 'answer' && <QuestionForm key={caseDetail.questionId} caseDetail={caseDetail} runId={runId} onResolved={onResolved} />}
      {/* A sent draft stays on screen, read-only, as the record of what was done. */}
      {caseDetail.suggestedAction.startsWith('email_') && <DraftEditor caseDetail={caseDetail} runId={runId} />}
      <section className={styles.done} aria-label="Marcar gestionado">
        {lead !== 'done' && <h3 className={styles.heading}>O ciérralo sin más</h3>}
        <TextField label="Nota (opcional)" value={note} onChange={setNote} hideLabel={lead !== 'done'} placeholder="Nota (opcional)" />
        <Button
          variant={lead === 'done' ? 'primary' : 'secondary'}
          leadingIcon={<Check />}
          onClick={markDone}
          loading={decide.isPending}
          className={styles.button}
        >
          Marcar gestionado
        </Button>
      </section>
    </div>
  )
}
