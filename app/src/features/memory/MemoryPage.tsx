import { useState } from 'react'
import { Plus } from 'lucide-react'
import { Button, Card, EmptyState, Metric, Page, PageHeader, Skeleton, TabPanel, Tabs } from '@/components'
import { useActiveRun, useMemoryRules, useRunStats } from '@/data'
import { formatNumber } from '@/lib/format'
import { useEntityScope, useTextParam } from '@/lib/urlState'
import { NewRuleDialog } from './NewRuleDialog'
import { PoliciesTab } from './PoliciesTab'
import { RuleList } from './RuleList'
import { rulesInScope } from './model'
import styles from './MemoryPage.module.css'

const TABS = [
  { id: 'reglas', label: 'Reglas' },
  { id: 'politicas', label: 'Políticas' },
]

export function MemoryPage() {
  const { runId, run } = useActiveRun()
  const [entity] = useEntityScope()
  const [tabParam, setTab] = useTextParam('pestana')
  const tab = TABS.some((t) => t.id === tabParam) ? tabParam! : 'reglas'
  const [creating, setCreating] = useState(false)
  const rulesQuery = useMemoryRules(runId)
  const statsQuery = useRunStats(runId, entity)
  const rules = rulesQuery.data ? rulesInScope(rulesQuery.data, entity) : null
  const applied = statsQuery.data?.byRule.find((r) => r.rule === 'MEMORY-RULE')

  return (
    <Page>
      <PageHeader
        title="Memoria y reglas"
        subtitle="Lo que el sistema ha aprendido de las decisiones de una persona. Cada regla cambia la próxima ejecución, no esta."
        actions={
          <Button variant="primary" leadingIcon={<Plus aria-hidden />} onClick={() => setCreating(true)}>
            Nueva regla
          </Button>
        }
      />

      <div className={styles.top}>
        <div className={styles.metrics}>
          <Card>
            <Metric
              label="Reglas activas"
              value={rules ? formatNumber(rules.length) : ''}
              loading={!rules}
              comparison={entity ? 'De esta sociedad y de todo el grupo' : 'En todo el grupo'}
            />
          </Card>
          <Card>
            <Metric
              label="Movimientos con regla de memoria"
              value={statsQuery.data ? formatNumber(applied?.txns ?? 0) : ''}
              loading={!statsQuery.data}
              comparison="En esta ejecución"
              hint="Movimientos cuya fila salió de una regla MEMORY-RULE."
            />
          </Card>
          <Card>
            <Metric
              label="Reglas aplicadas en la ejecución"
              value={formatNumber(run.memoryRulesApplied)}
              comparison="Todo el grupo"
              hint="Reglas de memoria que cargó esta ejecución al arrancar."
            />
          </Card>
        </div>
        <p className={styles.note}>Todavía no hay un dato por regla: la ejecución solo cuenta los movimientos de todas las reglas juntas.</p>
      </div>

      <Tabs tabs={TABS} value={tab} onChange={setTab} idPrefix="memoria" aria-label="Memoria y reglas" />
      <TabPanel idPrefix="memoria" id="reglas">
        {tab === 'reglas' &&
          (rulesQuery.error && !rules ? (
            <EmptyState title="No se pudieron cargar las reglas" description={rulesQuery.error.message} />
          ) : !rules ? (
            <Skeleton height={160} radius="var(--radius-lg)" />
          ) : (
            <RuleList runId={runId} rules={rules} />
          ))}
      </TabPanel>
      <TabPanel idPrefix="memoria" id="politicas">
        {tab === 'politicas' && <PoliciesTab />}
      </TabPanel>

      {creating && <NewRuleDialog runId={runId} onClose={() => setCreating(false)} />}
    </Page>
  )
}
