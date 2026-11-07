import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { Brain } from 'lucide-react'
import { Button, toast } from '@/components'
import { useAnswerQuestion } from '@/data'
import type { CaseDetail } from '@/domain'
import { useScopedTo } from '@/lib/urlState'
import { TextField } from './TextField'
import styles from './QuestionForm.module.css'

interface QuestionFormProps {
  caseDetail: CaseDetail
  runId: string
  /** The answer was saved: the case is no longer waiting. */
  onResolved?: () => void
}

/** The system's question about a case, its options, an optional note and, if offered, the memory rule it would create. */
export function QuestionForm({ caseDetail, runId, onResolved }: QuestionFormProps) {
  const question = caseDetail.question
  const [optionId, setOptionId] = useState(question?.defaultOption ?? '')
  const [note, setNote] = useState('')
  const [saveAsRule, setSaveAsRule] = useState(false)
  const answer = useAnswerQuestion(runId)
  const navigate = useNavigate()
  const scoped = useScopedTo()
  if (!question) return null

  // «Ninguna» leaves the movement as it was: there is nothing to remember.
  const ruleApplies = question.rulePreview != null && optionId !== 'none'
  const rule = ruleApplies && saveAsRule

  const submit = (e: FormEvent) => {
    e.preventDefault()
    answer.mutate(
      { questionId: question.questionId, optionId, note, saveAsRule: rule },
      {
        onSuccess: () => {
          if (rule) {
            toast.success('Respuesta registrada y regla guardada', {
              description: question.rulePreview?.description,
              action: { label: 'Ver en Memoria', onClick: () => navigate(scoped('/memoria')) },
              duration: 8000,
            })
          } else toast.success('Respuesta registrada')
          onResolved?.()
        },
        onError: (error) => toast.error('No se ha podido guardar la respuesta', { description: error.message }),
      },
    )
  }

  return (
    <form className={styles.form} onSubmit={submit}>
      <fieldset className={styles.options}>
        <legend className={styles.question}>{question.question}</legend>
        {question.options.map((option) => (
          <label key={option.id} className={styles.option}>
            <input type="radio" name={question.questionId} value={option.id} checked={optionId === option.id} onChange={() => setOptionId(option.id)} />
            <span>{option.label}</span>
          </label>
        ))}
      </fieldset>
      <TextField label="Nota (opcional)" value={note} onChange={setNote} rows={2} />
      {question.rulePreview && (
        <label className={styles.rule} data-disabled={!ruleApplies || undefined}>
          <input type="checkbox" checked={rule} disabled={!ruleApplies} onChange={(e) => setSaveAsRule(e.target.checked)} />
          <span className={styles.ruleText}>
            <span className={styles.ruleTitle}>
              <Brain aria-hidden /> Guardar como regla
            </span>
            <span className={styles.ruleDescription}>{question.rulePreview.description}</span>
          </span>
        </label>
      )}
      <Button type="submit" variant="primary" loading={answer.isPending}>
        Responder
      </Button>
    </form>
  )
}
