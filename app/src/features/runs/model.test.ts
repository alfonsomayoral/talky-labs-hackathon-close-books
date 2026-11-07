import { describe, expect, it } from 'vitest'
import type { RunSummary, Score } from '@/domain'
import { consoleStep, defaultPair, eventClock, failureCause, isRise, diffCounts, diffMetrics, diffSegments, isDrop, scoreReference, stageList } from './model'

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
  it('compares the served run with the previous one of its phase, scored or not, not with a newer run', () => {
    const runs = [
      run('h9', 'holdout', '2026-11-07T06:00:00Z', 90),
      { ...run('l2', 'live', '2026-11-07T04:00:00Z', null), served: true },
      run('l1', 'live', '2026-11-07T02:00:00Z', null),
      run('l3', 'live', '2026-11-07T05:00:00Z', null),
    ]
    expect(defaultPair(runs)).toEqual({ a: 'l1', b: 'l2' })
  })
  it('leaves the other side empty when the served run is the first of its phase', () => {
    expect(defaultPair([{ ...run('l1', 'live', '2026-11-07T02:00:00Z', null), served: true }, run('h1', 'holdout', '2026-11-07T01:00:00Z', 80)])).toEqual({ a: null, b: 'l1' })
  })
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

describe('failureCause', () => {
  it('keeps the cause of a traceback, not its frames', () => {
    const traceback = 'Traceback (most recent call last):\n  File "cli.py", line 22, in _cmd_run\n    run = run_pipeline()\n          ^^^^^^\npolars.exceptions.ColumnNotFoundError: bank_txn_id\n'
    expect(failureCause(traceback)).toBe('polars.exceptions.ColumnNotFoundError: bank_txn_id')
  })
  it('leaves a one-line message as it is, and nothing as nothing', () => {
    expect(failureCause('no output')).toBe('no output')
    expect(failureCause(null)).toBeNull()
    expect(failureCause('  \n ')).toBeNull()
  })
})

describe('isRise', () => {
  it('is only a real improvement', () => {
    expect(isRise({ key: 'x', a: 0.5, b: 0.6, delta: 0.1 })).toBe(true)
    expect(isRise({ key: 'x', a: 0.6, b: 0.5, delta: -0.1 })).toBe(false)
    expect(isRise({ key: 'x', a: 0.5, b: 0.5, delta: 0 })).toBe(false)
    expect(isRise({ key: 'x', a: null, b: 0.5, delta: null })).toBe(false)
  })
})

describe('eventClock', () => {
  const at = (time: string) => new Date(`2026-11-07T${time}:00+01:00`)

  it('counts down to the data, then to the close', () => {
    expect(eventClock(at('16:30'))).toBe('Faltan 1 h 30 min para los datos')
    expect(eventClock(at('18:00'))).toBe('Datos publicados: quedan 1 h 30 min para el cierre')
    expect(eventClock(at('19:25'))).toBe('Datos publicados: quedan 5 min para el cierre')
  })

  it('says when the window is over', () => {
    expect(eventClock(at('19:30'))).toBe('Envíos cerrados')
  })
})

describe('scoreReference', () => {
  it('takes the newest scored holdout', () => {
    const runs = [run('a', 'holdout', '2026-11-07T08:00', 91.2), run('b', 'holdout', '2026-11-07T09:00', 91.37), run('c', 'live', '2026-11-07T10:00', null), run('d', 'holdout', '2026-11-07T11:00', null)]
    expect(scoreReference(runs)?.runId).toBe('b')
  })

  it('is null without one', () => {
    expect(scoreReference([run('c', 'live', '2026-11-07T10:00', null)])).toBeNull()
  })
})
