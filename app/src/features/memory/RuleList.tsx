import { useState } from 'react'
import { Link } from 'react-router'
import { Brain, Trash2 } from 'lucide-react'
import { Badge, Button, Card, Dialog, EmptyState, IconButton, Mono, Pill, toast } from '@/components'
import { useMemoryRuleActions, useRunStats } from '@/data'
import type { MemoryRule } from '@/domain'
import { formatDateTime } from '@/lib/format'
import { useEntityScope, useScopedTo } from '@/lib/urlState'
import { keyParams, ruleKindLabel, runCommand } from './model'
import styles from './RuleList.module.css'

interface Props {
  runId: string
  rules: MemoryRule[]
}

export function RuleList({ runId, rules }: Props) {
  const [entity] = useEntityScope()
  const scoped = useScopedTo()
  const stats = useRunStats(runId, null)
  const entityName = (id: string) => stats.data?.byEntity.find((e) => e.entity === id)?.name ?? id
  const { remove } = useMemoryRuleActions(runId)
  const [removing, setRemoving] = useState<MemoryRule | null>(null)

  const link = (pathname: string, params: Record<string, string>) => {
    const base = scoped(pathname)
    return {
      pathname,
      search: `?${new URLSearchParams([...new URLSearchParams(base.search), ...Object.entries(params)])}`,
    }
  }

  const confirmRemove = () => {
    if (!removing) return
    remove.mutate(removing.ruleId, {
      onSuccess: () => {
        toast.success('Regla eliminada', {
          description: 'Deja de aplicarse en la siguiente ejecución.',
        })
        setRemoving(null)
      },
      onError: (error) =>
        toast.error('No se pudo eliminar la regla', {
          description: error.message,
        }),
    })
  }

  return (
    <div className={styles.wrap}>
      <p className={styles.how}>
        Una regla no cambia esta ejecución: se aplica en la siguiente, que las carga con <Mono>{runCommand(runId)}</Mono>. Lánzala desde{' '}
        <Link to={link('/ejecuciones', { vista: 'consola' })}>Ejecuciones</Link>.
      </p>

      {rules.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Brain />}
            title={entity ? 'Ninguna regla para esta sociedad' : 'Todavía no se ha enseñado nada al sistema'}
            description="Las reglas nacen al responder una pregunta de la bandeja y marcar «guardar como regla», o con «Nueva regla»."
          />
        </Card>
      ) : (
        <Card padding="none">
          <ul className={styles.list}>
            {rules.map((rule) => {
              const params = keyParams(rule)
              const caseId = rule.createdFrom.caseId
              return (
                <li key={rule.ruleId} className={styles.rule}>
                  <div className={styles.main}>
                    <p className={styles.description}>{rule.description}</p>
                    <div className={styles.tags}>
                      <Badge variant="outline">{ruleKindLabel(rule.kind)}</Badge>
                      {rule.scope.entity && <Pill>{entityName(rule.scope.entity)}</Pill>}
                      {params.map((p) => (
                        <span key={p.label} className={styles.param}>
                          {p.label} <Mono>{p.value}</Mono>
                        </span>
                      ))}
                    </div>
                    <p className={styles.meta}>
                      <Mono muted>{rule.ruleId}</Mono> · {rule.by} · {formatDateTime(rule.at)} ·{' '}
                      {caseId ? (
                        <Link to={link('/bandeja', { ver: caseId })}>
                          Origen: caso <Mono>{caseId}</Mono>
                        </Link>
                      ) : (
                        'Creada a mano'
                      )}
                    </p>
                  </div>
                  <IconButton icon={<Trash2 />} label={`Eliminar la regla ${rule.ruleId}`} onClick={() => setRemoving(rule)} />
                </li>
              )
            })}
          </ul>
        </Card>
      )}

      <Dialog
        open={removing != null}
        onClose={() => setRemoving(null)}
        title="Eliminar la regla"
        description={removing ? `${removing.ruleId}: ${removing.description}` : undefined}
        size="sm"
        footer={
          <>
            <Button onClick={() => setRemoving(null)}>Cancelar</Button>
            <Button variant="danger" loading={remove.isPending} onClick={confirmRemove}>
              Eliminar
            </Button>
          </>
        }
      >
        <p className={styles.confirm}>La siguiente ejecución dejará de aplicarla. Lo ya conciliado en esta no cambia.</p>
      </Dialog>
    </div>
  )
}
