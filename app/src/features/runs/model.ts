// Pure logic of the Ejecuciones screen: differences between two runs, the default pair to compare,
// the FINAL console's current step and the stage list. No React, no I/O.
import type { OfficialResult, RunSummary, RunState, Score } from '@/domain'
import { formatNumber } from '@/lib/format'

/** The official submission limit, uncompressed (`MAX_UNCOMPRESSED` in bankrec_score.py). */
export const SUBMISSION_LIMIT_BYTES = 60 * 1024 * 1024

/** The official limit of rows (`MAX_ROWS` in bankrec_score.py). */
export const SUBMISSION_LIMIT_ROWS = 3_000_000

/** Scored metrics in the order the scorer weighs them; the other keys in `score.metrics` are counters. */
export const METRIC_LABEL: Record<string, string> = {
  allocation_f1: 'F1 de pares',
  precision: 'Precisión',
  recall: 'Cobertura',
  txn_accuracy: 'Exactitud por movimiento',
  exception_macro_f1: 'F1 macro de excepciones',
}

export const STAGE_LABEL: Record<string, string> = {
  load: 'Carga',
  index: 'Índices',
  documents: 'Documentos',
  rules: 'Reglas',
  resolve: 'Resolución',
  output: 'Salida',
  score: 'Puntuación',
}

const EPSILON = 1e-9

export interface Delta {
  key: string
  a: number | null
  b: number | null
  /** `b - a`; null when one side is missing. */
  delta: number | null
  /** Movements in the segment (segments only). */
  n?: number
}

const delta = (a: number | null, b: number | null) => (a != null && b != null ? b - a : null)

export function diffMetrics(a: Score, b: Score): Delta[] {
  return Object.keys(METRIC_LABEL)
    .filter((key) => key in a.metrics || key in b.metrics)
    .map((key) => {
      const x = a.metrics[key] ?? null
      const y = b.metrics[key] ?? null
      return { key, a: x, b: y, delta: delta(x, y) }
    })
}

export const isDrop = (d: Delta) => d.delta != null && d.delta < -EPSILON
export const isRise = (d: Delta) => d.delta != null && d.delta > EPSILON

/** Every segment of either run; the ones that drop first, worst first, then by name. */
export function diffSegments(a: Score, b: Score): Delta[] {
  const keys = [...new Set([...Object.keys(a.segments), ...Object.keys(b.segments)])]
  const rows = keys.map((key) => {
    const x = a.segments[key]?.accuracy ?? null
    const y = b.segments[key]?.accuracy ?? null
    return { key, a: x, b: y, delta: delta(x, y), n: b.segments[key]?.n ?? a.segments[key]?.n }
  })
  return rows.sort((p, q) => Number(isDrop(q)) - Number(isDrop(p)) || (isDrop(p) ? p.delta! - q.delta! : 0) || p.key.localeCompare(q.key))
}

/** Rows per rule (or any count map): a rule missing from a run has no rows there. Biggest change first. */
export function diffCounts(a: Record<string, number>, b: Record<string, number>): Delta[] {
  const keys = [...new Set([...Object.keys(a), ...Object.keys(b)])]
  return keys
    .map((key) => ({ key, a: a[key] ?? 0, b: b[key] ?? 0, delta: (b[key] ?? 0) - (a[key] ?? 0) }))
    .sort((p, q) => Math.abs(q.delta) - Math.abs(p.delta) || p.key.localeCompare(q.key))
}

/** Latest scored run (b) against the previous scored run of its phase (a); with no scores, the two latest runs. */
export function defaultPair(runs: RunSummary[]): { a: string | null; b: string | null } {
  const byDate = [...runs].sort((p, q) => q.createdAt.localeCompare(p.createdAt))
  const served = byDate.find((r) => r.served)
  if (served) {
    const previous = byDate.find((r) => r.phase === served.phase && r.createdAt < served.createdAt)
    return { a: previous?.runId ?? null, b: served.runId }
  }
  const scored = byDate.filter((r) => r.score != null)
  const pool = scored.length ? scored : byDate
  const b = pool[0]
  if (!b) return { a: null, b: null }
  const a = scored.length ? pool.find((r) => r !== b && r.phase === b.phase) : pool[1]
  return { a: a?.runId ?? null, b: b.runId }
}

export type ConsoleStep = 1 | 2 | 3 | 4

/** Where the FINAL console stands: 1 choose the phase, 2 run it, 3 validate, 4 hand over to a person. */
export function consoleStep(s: { phase: string | null; status: RunState | null; validation: { ok: boolean } | null }): ConsoleStep {
  if (!s.phase) return 1
  if (s.status !== 'done') return 2
  return s.validation?.ok ? 4 : 3
}

export type StageState = 'done' | 'running' | 'pending'

// `score` only runs where the phase has official answers: it is not an expected stage.
const PIPELINE = Object.keys(STAGE_LABEL).filter((s) => s !== 'score')

/** Pipeline stages in order (then any other the run reports), with their state and milliseconds when done. */
export function stageList(done: Record<string, number>, current: string | null): { stage: string; state: StageState; ms: number | null }[] {
  const stages = [...PIPELINE, ...Object.keys(done).filter((s) => !PIPELINE.includes(s))]
  return stages.map((stage) => ({ stage, state: stage in done ? 'done' : stage === current ? 'running' : 'pending', ms: done[stage] ?? null }))
}

/** `34,1 MB`, `820 KB`. */
export function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${formatNumber(bytes / 1024 / 1024, { decimals: 1 })} MB`
  return `${formatNumber(Math.round(bytes / 1024))} KB`
}

/** What a person can act on from a failed run: the error is the tail of the process output, often a traceback. */
export function failureCause(error: string | null | undefined): string | null {
  const lines = (error ?? '').split('\n').map((l) => l.trim()).filter(Boolean)
  return lines.at(-1) ?? null
}

// The event's window (PROBLEM.md): FINAL's data are published at 18:00 and submissions close at 19:30, Madrid time.
const DATA_AT = Date.parse('2026-11-07T18:00:00+01:00')
const CLOSE_AT = Date.parse('2026-11-07T19:30:00+01:00')

const untilLabel = (ms: number) => {
  const minutes = Math.ceil(ms / 60_000)
  const hours = Math.floor(minutes / 60)
  return hours > 0 ? `${hours} h ${minutes % 60} min` : `${minutes} min`
}

export function eventClock(now: Date): string {
  const t = now.getTime()
  if (t < DATA_AT) return `Faltan ${untilLabel(DATA_AT - t)} para los datos`
  if (t < CLOSE_AT) return `Datos publicados: quedan ${untilLabel(CLOSE_AT - t)} para el cierre`
  return 'Envíos cerrados'
}

/** The score of the run the API serves: the others are experiments. */
export const scoreReference = (runs: RunSummary[]): RunSummary | null => runs.find((r) => r.served && r.score != null) ?? null

/** The official result of a run, if the API sends one. */
export const officialResultOf = (runs: RunSummary[], runId: string | null | undefined): OfficialResult | null => runs.find((r) => r.runId === runId)?.officialResult ?? null
