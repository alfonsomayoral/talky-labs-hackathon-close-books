// Pure logic of the Ejecuciones screen: differences between two runs, the default pair to compare,
// the FINAL console's current step and the stage list. No React, no I/O.
import type { RunSummary, RunState, Score } from '@/domain'
import { formatNumber } from '@/lib/format'

/** The official submission limit, uncompressed (`MAX_UNCOMPRESSED` in bankrec_score.py). */
export const SUBMISSION_LIMIT_BYTES = 60 * 1024 * 1024

/** Scored metrics in the order the scorer weighs them; the other keys in `score.metrics` are counters. */
export const METRIC_LABEL: Record<string, string> = {
  allocation_f1: 'F1 de asignación',
  precision: 'Precisión',
  recall: 'Cobertura',
  txn_accuracy: 'Acierto por movimiento',
  exception_macro_f1: 'F1 macro de excepciones',
}

export const STAGE_LABEL: Record<string, string> = {
  load: 'Carga',
  index: 'Índices',
  documents: 'Documentos',
  rules: 'Reglas',
  resolve: 'Resolución',
  output: 'Salida',
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

const PIPELINE = Object.keys(STAGE_LABEL)

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
