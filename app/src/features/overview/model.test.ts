import { describe, expect, it } from 'vitest'
import type { DayStats, RunStats } from '@/domain'
import { dayChart, headline, amountSplit, modelTotals, monthTicks, nearestIndex, scoreMetrics, segmentsWorstFirst } from './model'

const day = (date: string, txns: number, txnsAuto: number): DayStats => ({ date, txns, txnsAuto, reviewQueue: txns - txnsAuto, identifiedEur: 0 })

const plain = (text: string) => text.replace(/\s/g, ' ')

describe('headline', () => {
  it('groups thousands in the number of waiting cases', () => {
    expect(plain(headline({ txns: 203083, txnsAuto: 0, reviewQueue: 203083 }))).toContain('203.083 casos esperan')
  })
  it('states the auto rate and how many cases wait for a person', () => {
    expect(plain(headline({ txns: 800, txnsAuto: 600, reviewQueue: 40 }))).toBe('75 % conciliado sin intervención; 40 casos esperan a una persona')
  })
  it('uses the singular for one case and says so when the queue is empty', () => {
    expect(headline({ txns: 10, txnsAuto: 9, reviewQueue: 1 })).toContain('1 caso espera')
    expect(plain(headline({ txns: 10, txnsAuto: 10, reviewQueue: 0 }))).toBe('100 % conciliado sin intervención; nada espera a una persona')
  })
  it('does not divide by zero', () => {
    expect(headline({ txns: 0, txnsAuto: 0, reviewQueue: 0 })).toBe('Sin movimientos en este alcance')
  })
})

describe('dayChart', () => {
  it('splits each day into auto and queue movements, never negative, and finds the tallest day', () => {
    const chart = dayChart([day('2025-07-01', 7, 3), day('2025-07-02', 2, 2), { ...day('2025-07-03', 1, 0), txnsAuto: 2 }])
    expect(chart.days.map((d) => [d.auto, d.queue])).toEqual([[3, 4], [2, 0], [2, 0]])
    expect(chart.max).toBe(7)
  })
  it('has a usable max with no days', () => {
    expect(dayChart([]).max).toBe(1)
  })
})

describe('nearestIndex', () => {
  it('maps a pointer x to the column under it and clamps to the ends', () => {
    expect(nearestIndex(0, 100, 10)).toBe(0)
    expect(nearestIndex(55, 100, 10)).toBe(5)
    expect(nearestIndex(-20, 100, 10)).toBe(0)
    expect(nearestIndex(500, 100, 10)).toBe(9)
    expect(nearestIndex(10, 100, 0)).toBe(-1)
  })
})

describe('monthTicks', () => {
  it('marks the first day of each month present', () => {
    const days = [day('2025-07-30', 1, 1), day('2025-07-31', 1, 1), day('2025-08-01', 1, 1), day('2025-08-02', 1, 1), day('2025-09-03', 1, 1)]
    expect(monthTicks(days)).toEqual([
      { index: 2, month: '2025-08' },
      { index: 4, month: '2025-09' },
    ])
  })
})

describe('score', () => {
  const score = {
    score: 70,
    metrics: { allocation_f1: 0.8, txn_accuracy: 0.7, exception_macro_f1: 0.5, precision: 1 },
    segments: { a: { n: 10, accuracy: 0.9 }, b: { n: 20, accuracy: 0.4 }, c: { n: 5, accuracy: 0.4 } },
  }
  it('reads the three metrics that make up the score, in the order of their weights', () => {
    expect(scoreMetrics(score).map((m) => [m.key, m.value])).toEqual([
      ['allocation_f1', 0.8],
      ['txn_accuracy', 0.7],
      ['exception_macro_f1', 0.5],
    ])
  })
  it('orders segments worst first, breaking ties by size', () => {
    expect(segmentsWorstFirst(score).map((s) => s.key)).toEqual(['b', 'c', 'a'])
  })
})

describe('modelTotals', () => {
  it('adds calls and cost across models', () => {
    const models = { x: { calls: 3, inputTokens: 0, outputTokens: 0, costUsd: 0.5 }, y: { calls: 2, inputTokens: 0, outputTokens: 0, costUsd: 0.25 } }
    expect(modelTotals(models)).toEqual({ calls: 5, costUsd: 0.75 })
  })
})

describe('amountSplit', () => {
  it('splits the whole amount into settled against items, in the queue, and the rest, which are categories', () => {
    expect(amountSplit({ identifiedEur: 312, reviewQueueEur: 34, totalEur: 1000 })).toEqual({ items: 0.312, categories: 0.654, queue: 0.034 })
  })
  it('never gives a negative share if the queue and the items overlap', () => {
    expect(amountSplit({ identifiedEur: 700, reviewQueueEur: 400, totalEur: 1000 }).categories).toBe(0)
  })
  it('gives nothing with no amount', () => {
    expect(amountSplit({ identifiedEur: 0, reviewQueueEur: 0, totalEur: 0 })).toBeNull()
  })
})
