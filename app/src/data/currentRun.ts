// Which run the app is looking at: `?run=` in the URL, else the latest LIVE, else the latest of any phase.
import type { RunSummary } from '@/domain'
import { useRunParam } from '@/lib/urlState'
import { useRuns } from './api/queries'

export function chooseRun(runs: RunSummary[], wanted: string | null): RunSummary | null {
  if (wanted) return runs.find((r) => r.runId === wanted) ?? null
  const byDate = [...runs].sort((a, b) => b.createdAt.localeCompare(a.createdAt))
  return byDate.find((r) => r.phase === 'live') ?? byDate[0] ?? null
}

export function useCurrentRun() {
  const [wanted] = useRunParam()
  const runs = useRuns()
  const run = runs.data ? chooseRun(runs.data, wanted) : null
  return { run, runId: run?.runId ?? null, phase: run?.phase ?? null, runs: runs.data ?? [], loading: runs.isPending, error: runs.error }
}

/** For screens under the shell's gate, which only renders them once there is a run. */
export function useActiveRun() {
  const { run } = useCurrentRun()
  if (!run) throw new Error('useActiveRun outside the run gate')
  return { runId: run.runId, phase: run.phase, run }
}
