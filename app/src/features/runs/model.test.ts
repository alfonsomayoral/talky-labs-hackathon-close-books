import { describe, expect, it } from 'vitest'
import type { RunSummary, Score } from '@/domain'
import { consoleStep, defaultPair, diffCounts, diffMetrics, diffSegments, isDrop, stageList } from './model'

const score = (metrics: Record<string, number>, segments: Score['segments'] = {}): Score => ({ score: 0, metrics, segments })
const run = (runId: string, phase: string, createdAt: string, s: number | null) => ({ runId, phase, createdAt, score: s }) as RunSummary

describe('diffMetrics', () => {
  it('gives b minus a for the official metrics, in a fixed order, and ignores the counters', () => {
    const a = score({ txn_accuracy: 0.6, allocation_f1: 0.8, rows: 10 })
    const b = score({ txn_accuracy: 0.7, allocation_f1: 0.75, rows: 12 })
    const d = diffMetrics(a, b)
    expect(d.map((x) => x.key)).toEqual(['allocation_f1', 'txn_accuracy'])
    expect(d[0].delta).toBeCloseTo(-0.05)
    expect(d[1].delta).toBeCloseTo(0.1)
  })
})

describe('diffSegments', () => {
  const a = score({}, { x: { n: 10, accuracy: 0.9 }, y: { n: 5, accuracy: 0.5 }, gone: { n: 2, accuracy: 1 } })
  const b = score({}, { x: { n: 10, accuracy: 0.8 }, y: { n: 5, accuracy: 0.6 }, fresh: { n: 3, accuracy: 0.4 } })
  const d = diffSegments(a, b)

  it('puts the segments that drop first, worst first', () => {
    expect(d[0].key).toBe('x')
    expect(isDrop(d[0])).toBe(true)
    expect(d.filter(isDrop)).toHaveLength(1)
  })
  it('keeps segments present in only one run, without a delta', () => {
    const gone = d.find((x) => x.key === 'gone')!
    const fresh = d.find((x) => x.key === 'fresh')!
    expect([gone.b, gone.delta]).toEqual([null, null])
    expect([fresh.a, fresh.delta, fresh.n]).toEqual([null, null, 3])
    expect(isDrop(gone)).toBe(false)
  })
  it('does not call a rounding wobble a drop', () => {
    const same = diffSegments(score({}, { x: { n: 1, accuracy: 0.5 } }), score({}, { x: { n: 1, accuracy: 0.5 - 1e-12 } }))
    expect(isDrop(same[0])).toBe(false)
  })
})

describe('diffCounts', () => {
  it('treats a rule missing from a run as zero rows and orders by size of change', () => {
    const d = diffCounts({ A: 100, B: 50, C: 7 }, { A: 90, C: 7, D: 30 })
    expect(d.map((x) => [x.key, x.delta])).toEqual([
      ['B', -50],
      ['D', 30],
      ['A', -10],
      ['C', 0],
    ])
  })
})

describe('defaultPair', () => {
  it('compares the latest scored run with the previous scored one of the same phase', () => {
    const runs = [
      run('h3', 'holdout', '2026-11-07T05:00:00Z', 80),
      run('l1', 'live', '2026-11-07T04:00:00Z', null),
      run('h2', 'holdout', '2026-11-07T03:00:00Z', 70),
      run('h1', 'holdout', '2026-11-07T01:00:00Z', null),
    ]
    expect(defaultPair(runs)).toEqual({ a: 'h2', b: 'h3' })
  })
  it('falls back to the two latest runs when none has a score', () => {
    const runs = [run('l2', 'live', '2026-11-07T04:00:00Z', null), run('l1', 'live', '2026-11-07T01:00:00Z', null)]
    expect(defaultPair(runs)).toEqual({ a: 'l1', b: 'l2' })
  })
  it('leaves what it cannot fill empty', () => {
    expect(defaultPair([])).toEqual({ a: null, b: null })
    expect(defaultPair([run('l1', 'live', '2026-11-07T01:00:00Z', 5)])).toEqual({ a: null, b: 'l1' })
  })
})

describe('consoleStep', () => {
  const ok = { ok: true }
  it('walks from choosing the phase to the hand-off to a person', () => {
    expect(consoleStep({ phase: null, status: null, validation: null })).toBe(1)
    expect(consoleStep({ phase: 'final', status: null, validation: null })).toBe(2)
    expect(consoleStep({ phase: 'final', status: 'running', validation: null })).toBe(2)
    expect(consoleStep({ phase: 'final', status: 'done', validation: null })).toBe(3)
    expect(consoleStep({ phase: 'final', status: 'done', validation: ok })).toBe(4)
  })
  it('stays on validation while the file is invalid, and on running when the run failed', () => {
    expect(consoleStep({ phase: 'final', status: 'done', validation: { ok: false } })).toBe(3)
    expect(consoleStep({ phase: 'final', status: 'failed', validation: null })).toBe(2)
  })
})

describe('stageList', () => {
  it('marks done, running and pending stages in pipeline order, keeping unknown stages', () => {
    const rows = stageList({ load: 10, rules: 30, extra: 5 }, 'index')
    expect(rows.map((r) => [r.stage, r.state])).toEqual([
      ['load', 'done'],
      ['index', 'running'],
      ['documents', 'pending'],
      ['rules', 'done'],
      ['resolve', 'pending'],
      ['output', 'pending'],
      ['extra', 'done'],
    ])
  })
})
