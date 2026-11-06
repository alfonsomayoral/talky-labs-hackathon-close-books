// Pure calculations of the Resumen screen.
import type { DayStats, ModelUsage, RunStats, Score } from '@/domain'
import { autoRate } from '@/domain'
import { formatNumber, formatPercent } from '@/lib/format'

export function headline(s: Pick<RunStats, 'txns' | 'txnsAuto' | 'reviewQueue'>): string {
  const rate = autoRate(s)
  if (rate == null) return 'Sin movimientos en este alcance'
  const waiting = s.reviewQueue === 0 ? 'nada espera a una persona' : `${formatNumber(s.reviewQueue)} ${s.reviewQueue === 1 ? 'caso espera' : 'casos esperan'} a una persona`
  return `${formatPercent(rate, { decimals: 0 })} conciliado sin intervención; ${waiting}`
}

export const identifiedShare = (s: Pick<RunStats, 'identifiedEur' | 'totalEur'>) => (s.totalEur > 0 ? s.identifiedEur / s.totalEur : null)

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
