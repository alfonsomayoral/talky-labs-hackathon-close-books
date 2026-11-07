// Pure calculations of the Resumen screen.
import type { DayStats, EvidenceGroup, ModelUsage, QueueId, RunStats, Score } from '@/domain'
import { EXCEPTION_DEFINITION, autoRate, evidenceOf } from '@/domain'
import { formatNumber, formatPercent } from '@/lib/format'

type Totals = Record<QueueId, { cases: number }>

/** A big count at a glance: `235`, `18,0 k`. */
const shortCount = (n: number) => (n < 1000 ? formatNumber(n) : `${formatNumber(n / 1000, { decimals: 1 })} k`)

export function headline(s: Pick<RunStats, 'txns' | 'txnsAuto'>, totals: Totals | null): string {
  const rate = autoRate(s)
  if (rate == null) return 'Sin movimientos en este alcance'
  const parts = [`${formatPercent(rate, { decimals: 0 })} de los movimientos conciliados sin intervención`]
  if (totals) {
    const { decidir, revisar, reclamar } = totals
    if (decidir.cases) parts.push(`${shortCount(decidir.cases)} ${decidir.cases === 1 ? 'decisión' : 'decisiones'}`)
    if (revisar.cases) parts.push(`${shortCount(revisar.cases)} por revisar`)
    if (reclamar.cases) parts.push(`${shortCount(reclamar.cases)} en cobros`)
  }
  return parts.join(' · ')
}

/** Calendar months a period touches. */
export function periodMonths(from: string, to: string): number {
  const month = (date: string) => Number(date.slice(0, 4)) * 12 + Number(date.slice(5, 7))
  return month(to) - month(from) + 1
}

/** The whole amount, as shares: settled against items, waiting in the queue, and the rest, which only got a category. */
export function amountSplit(s: Pick<RunStats, 'identifiedEur' | 'reviewQueueEur' | 'totalEur'>): { items: number; categories: number; queue: number } | null {
  if (s.totalEur <= 0) return null
  return { items: s.identifiedEur / s.totalEur, categories: Math.max(0, s.totalEur - s.identifiedEur - s.reviewQueueEur) / s.totalEur, queue: s.reviewQueueEur / s.totalEur }
}

export interface ChartDay {
  date: string
  auto: number
  queue: number
}

/** Movements per day split into closed alone and in the queue; `max` is the tallest day. */
export function dayChart(byDay: DayStats[]): { days: ChartDay[]; max: number } {
  const days = byDay.map((d) => ({ date: d.date, auto: d.txnsAuto, queue: Math.max(d.txns - d.txnsAuto, 0) }))
  return { days, max: Math.max(1, ...days.map((d) => d.auto + d.queue)) }
}

/** Column under a pointer: `x` pixels from the left of a plot `width` wide with `count` columns, or -1 with none. */
export function nearestIndex(x: number, width: number, count: number): number {
  if (count === 0 || width <= 0) return -1
  return Math.min(count - 1, Math.max(0, Math.floor((x / width) * count)))
}

/** First column of every month after the first one shown. */
export function monthTicks(days: Pick<ChartDay, 'date'>[]): { index: number; month: string }[] {
  const ticks: { index: number; month: string }[] = []
  days.forEach((d, index) => {
    const month = d.date.slice(0, 7)
    if (index > 0 && month !== days[index - 1].date.slice(0, 7)) ticks.push({ index, month })
  })
  return ticks
}

// Keys of the official scorer (`bankrec_score.py`): the score is 0.5 allocation F1 + 0.3 transaction accuracy + 0.2 exception macro F1.
const SCORE_METRICS = [
  { key: 'allocation_f1', label: 'F1 de asignaciones', weight: 0.5 },
  { key: 'txn_accuracy', label: 'Movimientos exactos', weight: 0.3 },
  { key: 'exception_macro_f1', label: 'F1 de excepciones', weight: 0.2 },
] as const

export const scoreMetrics = (score: Score) => SCORE_METRICS.filter((m) => score.metrics[m.key] != null).map((m) => ({ ...m, value: score.metrics[m.key] }))

/** Segments of the golden (`{ n, accuracy }`), the weakest first. */
export const segmentsWorstFirst = (score: Score) =>
  Object.entries(score.segments)
    .map(([key, v]) => ({ key, n: v.n, accuracy: v.accuracy }))
    .sort((a, b) => a.accuracy - b.accuracy || b.n - a.n)

export const modelTotals = (models: Record<string, ModelUsage>) =>
  Object.values(models).reduce((t, m) => ({ calls: t.calls + m.calls, costUsd: t.costUsd + m.costUsd }), { calls: 0, costUsd: 0 })

/** Movements by the kind of source that backs them, largest first. Every movement has one rule, so shares add up to 1. */
export function evidenceBreakdown(byRule: RunStats['byRule'], total: number) {
  const add = <K,>(map: Map<K, number>, key: K, txns: number) => map.set(key, (map.get(key) ?? 0) + txns)
  const sources = new Map<string, number>()
  const groups = new Map<EvidenceGroup, number>()
  for (const r of byRule) {
    const { source, group } = evidenceOf(r.rule)
    add(sources, source, r.txns)
    add(groups, group, r.txns)
  }
  const share = (txns: number) => (total > 0 ? txns / total : 0)
  return {
    groups: [...groups].map(([group, txns]) => ({ group, txns, share: share(txns) })).sort((a, b) => b.txns - a.txns),
    sources: [...sources].map(([source, txns]) => ({ source, txns, share: share(txns) })).sort((a, b) => b.txns - a.txns),
  }
}

/** The closed list of exceptions: what occurred, largest first, and then what did not. */
export function closedExceptions(byException: RunStats['byException']): RunStats['byException'] {
  const seen = new Set(byException.map((e) => e.exception))
  return [...byException, ...Object.keys(EXCEPTION_DEFINITION).filter((e) => !seen.has(e)).map((exception) => ({ exception, rows: 0, amountEur: 0 }))]
}
