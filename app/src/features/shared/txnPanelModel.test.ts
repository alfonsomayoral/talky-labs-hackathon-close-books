import { describe, expect, it } from 'vitest'
import type { DetailRow } from '@/domain'
import { decisionOf, distinctParties, soleParty, submissionLines, sumByCurrency } from './txnPanelModel'

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

describe('distinctParties', () => {
  it('counts the parties of the items: a payment run pays several suppliers', () => {
    const rows = [{ item: { partyId: 'S1' } }, { item: { partyId: 'S2' } }, { item: { partyId: 'S1' } }, { item: null }] as DetailRow[]
    expect(distinctParties(rows)).toBe(2)
  })
})

describe('soleParty', () => {
  it('names the party when all the items are of the same one, as in a remittance advice', () => {
    const rows = [{ item: { partyId: 'C1', partyName: 'Navarro GmbH' } }, { item: { partyId: 'C1', partyName: 'Navarro GmbH' } }, { item: null }] as DetailRow[]
    expect(soleParty(rows)).toEqual({ partyId: 'C1', partyName: 'Navarro GmbH' })
  })

  it('names nobody with several parties or none', () => {
    expect(soleParty([{ item: { partyId: 'C1', partyName: 'A' } }, { item: { partyId: 'C2', partyName: 'B' } }] as DetailRow[])).toBeNull()
    expect(soleParty([{ item: null }] as DetailRow[])).toBeNull()
  })
})

describe('submissionLines', () => {
  it('writes the rows as the delivered CSV does: dot decimals, empty fields', () => {
    expect(
      submissionLines('BT-1', [
        { itemId: 'ARI-1', amountCents: 272773, category: null, exception: null },
        { itemId: 'ARI-2', amountCents: 500, category: null, exception: 'PARTIAL' },
      ]),
    ).toEqual(['bank_txn_id,item_id,amount,category,exception', 'BT-1,ARI-1,2727.73,,', 'BT-1,ARI-2,5.00,,PARTIAL'])
  })

  it('leaves item and amount empty on a row that settles no item', () => {
    expect(submissionLines('BT-2', [{ itemId: null, amountCents: null, category: 'BANK_FEES', exception: null }])[1]).toBe('BT-2,,,BANK_FEES,')
  })
})
