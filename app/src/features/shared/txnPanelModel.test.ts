import { describe, expect, it } from 'vitest'
import type { DetailRow } from '@/domain'
import { decisionOf, sumByCurrency } from './txnPanelModel'

describe('sumByCurrency', () => {
  it('never adds different currencies, and skips rows with no amount', () => {
    const rows = [
      { amountCents: 1000, currency: 'EUR' },
      { amountCents: 250, currency: 'EUR' },
      { amountCents: 9000, currency: 'MXN' },
      { amountCents: null, currency: null },
    ] as DetailRow[]
    expect(sumByCurrency(rows)).toEqual([
      { currency: 'EUR', cents: 1250 },
      { currency: 'MXN', cents: 9000 },
    ])
  })
})

describe('decisionOf', () => {
  it('lists each rule once, in order, and takes the lowest confidence', () => {
    const rows = [
      { rule: 'FILE-DD-BATCH', confidence: 1 },
      { rule: 'FILE-DD-BATCH', confidence: 0.95 },
      { rule: 'FALLBACK-UNIDENTIFIED', confidence: 0.4 },
    ] as DetailRow[]
    expect(decisionOf(rows)).toEqual({ rules: ['FILE-DD-BATCH', 'FALLBACK-UNIDENTIFIED'], confidence: 0.4 })
  })

  it('has no confidence when the movement has no rows', () => {
    expect(decisionOf([])).toEqual({ rules: [], confidence: null })
  })
})
