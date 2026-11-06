import { useId, useState } from 'react'
import { Button, Dialog, toast } from '@/components'
import { useMemoryRuleActions, useRunStats } from '@/data'
import type { MemoryRuleKind } from '@/domain'
import { useEntityScope } from '@/lib/urlState'
import { RULE_KINDS, cleanParams, describeRule, validateDescription, validateParams, type Params } from './model'
import styles from './NewRuleDialog.module.css'

interface Props {
  runId: string
  onClose: () => void
}

export function NewRuleDialog({ runId, onClose }: Props) {
  const formId = useId()
  const [scopeEntity] = useEntityScope()
  const stats = useRunStats(runId, null)
  const { create } = useMemoryRuleActions(runId)
  const [kind, setKind] = useState<MemoryRuleKind>('payer_is_customer')
  const [values, setValues] = useState<Params>({})
  const [entity, setEntity] = useState(scopeEntity ?? '')
  const [edited, setEdited] = useState<string | null>(null)
  const [tried, setTried] = useState(false)

  const spec = RULE_KINDS.find((k) => k.kind === kind)!
  const params = cleanParams(values)
  const errors = validateParams(kind, params)
  const valid = Object.keys(errors).length === 0
  const description = edited ?? (valid ? describeRule(kind, params) : '')
  const descriptionError = validateDescription(description)
  // An empty description is only worth flagging once the fields can write it.
  const descriptionShown = tried && descriptionError != null && (valid || edited != null)
  const show = (name: string) => (tried ? errors[name] : undefined)

  const changeKind = (next: MemoryRuleKind) => {
    setKind(next)
    setValues({})
    setEdited(null)
    setTried(false)
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setTried(true)
    if (!valid || descriptionError) return
    create.mutate(
      {
        kind,
        params,
        description: description.trim(),
        scope: entity ? { entity } : {},
        createdFrom: {},
      },
      {
        onSuccess: (rule) => {
          toast.success('Regla creada', {
            description: `${rule.ruleId}: se aplicará en la siguiente ejecución.`,
          })
          onClose()
        },
        onError: (error) =>
          toast.error('No se pudo crear la regla', {
            description: error.message,
          }),
      },
    )
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title="Nueva regla"
      description={spec.summary}
      footer={
        <>
          <Button onClick={onClose}>Cancelar</Button>
          <Button type="submit" form={formId} variant="primary" loading={create.isPending}>
            Crear regla
          </Button>
        </>
      }
    >
      <form id={formId} className={styles.form} onSubmit={submit} noValidate>
        <label className={styles.field}>
          <span className={styles.label}>Tipo</span>
          <select className={styles.control} value={kind} onChange={(e) => changeKind(e.target.value as MemoryRuleKind)}>
            {RULE_KINDS.map((k) => (
              <option key={k.kind} value={k.kind}>
                {k.label}
              </option>
            ))}
          </select>
        </label>

        {spec.fields.map((f) => {
          const error = show(f.name)
          return (
            <label key={f.name} className={styles.field}>
              <span className={styles.label}>{f.label}</span>
              <input
                className={`${styles.control} ${f.mono ? styles.mono : ''}`}
                value={values[f.name] ?? ''}
                placeholder={f.placeholder}
                autoComplete="off"
                spellCheck={false}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? `${formId}-${f.name}` : undefined}
                onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
              />
              {error && (
                <span id={`${formId}-${f.name}`} className={styles.error}>
                  {error}
                </span>
              )}
            </label>
          )
        })}

        <label className={styles.field}>
          <span className={styles.label}>Alcance</span>
          <select className={styles.control} value={entity} onChange={(e) => setEntity(e.target.value)}>
            <option value="">Todo el grupo</option>
            {stats.data?.byEntity.map((e) => (
              <option key={e.entity} value={e.entity}>
                {e.name}
              </option>
            ))}
          </select>
        </label>

        <label className={styles.field}>
          <span className={styles.label}>Descripción</span>
          <textarea
            className={styles.control}
            rows={2}
            value={description}
            placeholder="Se escribe sola al rellenar los campos"
            aria-invalid={descriptionShown ? true : undefined}
            onChange={(e) => setEdited(e.target.value)}
          />
          {descriptionShown && <span className={styles.error}>{descriptionError}</span>}
        </label>
      </form>
    </Dialog>
  )
}
