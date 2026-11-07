import { useMemo } from 'react'
import { Play, CloudOff } from 'lucide-react'
import { Amount, Badge, Button, Card, DataTable, EmptyState, Mono, Skeleton, type Column } from '@/components'
import { useCurrentRun, useRun, useRuns } from '@/data'
import { INBOX_STATUSES, type RunSummary } from '@/domain'
import { formatDateTime, formatDuration, formatNumber } from '@/lib/format'
import { useOpenObject } from '@/lib/urlState'
import { RunPanel } from './RunPanel'
import { ScoreExplainer } from './ScoreExplainer'
import styles from './RunsPage.module.css'

const queue = (r: RunSummary) => INBOX_STATUSES.reduce((sum, s) => sum + (r.cases[s] ?? 0), 0)

const COLUMNS: Column<RunSummary>[] = [
  { id: 'runId', header: 'Ejecución', width: 'minmax(210px, 1.4fr)', cell: (r) => <Mono>{r.runId}</Mono>, sortValue: (r) => r.runId },
  { id: 'phase', header: 'Fase', width: 100, cell: (r) => <Badge variant="outline">{r.phase}</Badge>, sortValue: (r) => r.phase },
  { id: 'createdAt', header: 'Fecha', width: 150, cell: (r) => formatDateTime(r.createdAt), sortValue: (r) => r.createdAt },
  { id: 'commit', header: 'Commit', width: 90, cell: (r) => <Mono>{r.gitCommit}</Mono> },
  { id: 'duration', header: 'Duración', width: 110, align: 'right', cell: (r) => formatDuration(r.durationMs), sortValue: (r) => r.durationMs },
  { id: 'txns', header: 'Movimientos', width: 110, align: 'right', cell: (r) => formatNumber(r.txns), sortValue: (r) => r.txns },
  { id: 'rows', header: 'Filas', width: 90, align: 'right', cell: (r) => formatNumber(r.rows), sortValue: (r) => r.rows },
  { id: 'queue', header: 'En cola', width: 90, align: 'right', cell: (r) => formatNumber(queue(r)), sortValue: queue },
  { id: 'calls', header: 'Llamadas', width: 90, align: 'right', cell: (r) => formatNumber(r.modelCalls), sortValue: (r) => r.modelCalls },
  { id: 'cost', header: 'Coste', width: 90, align: 'right', cell: (r) => <Amount cents={Math.round(r.modelCostUsd * 100)} currency="USD" />, sortValue: (r) => r.modelCostUsd },
  { id: 'score', header: 'Puntuación', width: 110, align: 'right', cell: (r) => formatNumber(r.score, { decimals: 2 }), sortValue: (r) => r.score },
]

export function HistoryTab({ onGoToConsole }: { onGoToConsole: () => void }) {
  const runs = useRuns()
  const [openId, setOpenId] = useOpenObject()
  const rows = useMemo(() => runs.data ?? [], [runs.data])
  const current = useRun(useCurrentRun().runId).data

  if (runs.isPending) return <Skeleton height={240} />
  if (runs.error) return <EmptyState icon={<CloudOff />} title="No se ha podido cargar el historial" description={runs.error.message} />

  return (
    <>
      <Card className={styles.score}>
        <ScoreExplainer score={current?.score ?? null} runs={rows} />
      </Card>
      <DataTable
        aria-label="Historial de ejecuciones"
        rows={rows}
        columns={COLUMNS}
        getRowId={(r) => r.runId}
        selectedId={openId}
        onSelectedChange={(id) => openId && id && setOpenId(id)}
        onOpen={(r) => setOpenId(r.runId)}
        globalKeys
        empty={
          <EmptyState
            size="sm"
            icon={<Play />}
            title="Todavía no hay ninguna ejecución"
            description="Lanza la primera desde la consola."
            action={<Button onClick={onGoToConsole}>Ir a la consola</Button>}
          />
        }
      />
      <RunPanel runId={openId} onClose={() => setOpenId(null)} />
    </>
  )
}
