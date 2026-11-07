import { describe, expect, it } from 'vitest'
import type { RunSummary } from '@/domain'
import { chooseRun } from './currentRun'

const run = (runId: string, phase: string, createdAt: string) => ({ runId, phase, createdAt }) as RunSummary

describe('chooseRun', () => {
  const runs = [run('holdout-new', 'holdout', '2026-11-07T05:00:00Z'), run('live-old', 'live', '2026-11-07T01:00:00Z'), run('live-new', 'live', '2026-11-07T03:00:00Z')]

  it('prefers the latest LIVE over a newer run of another phase', () => {
    expect(chooseRun(runs, null)?.runId).toBe('live-new')
  })
  it('falls back to the latest of any phase when there is no LIVE', () => {
    expect(chooseRun(runs.slice(0, 1), null)?.runId).toBe('holdout-new')
  })
  it('prefers the run the server was started with over a newer LIVE', () => {
    const served = { ...run('live-old', 'live', '2026-11-07T01:00:00Z'), served: true }
    expect(chooseRun([...runs.filter((r) => r.runId !== 'live-old'), served], null)?.runId).toBe('live-old')
  })
  it('honours the run in the URL, and reports a wrong one instead of showing another', () => {
    expect(chooseRun(runs, 'live-old')?.runId).toBe('live-old')
    expect(chooseRun(runs, 'nope')).toBeNull()
  })
})
