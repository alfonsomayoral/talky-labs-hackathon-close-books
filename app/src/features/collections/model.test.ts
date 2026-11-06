import { describe, expect, it } from 'vitest'
import type { AgingParty } from '@/domain'
import { filterParties, riskOf, sortFromParam, sortToParam } from './model'

const party = (over: Partial<AgingParty> = {}): AgingParty => ({
  partyId: 'C1',
  partyName: 'Acme',
  entity: 'ES00',
  openEur: 100_00,
  overdueEur: 0,
  buckets: { not_due: 100_00, d1_30: 0, d31_60: 0, d61_90: 0, d90_plus: 0 },
  openItems: 1,
  oldestDaysOverdue: 0,
  disputes: 0,
  duplicates: 0,
  caseId: null,
  ...over,
})

describe('riskOf', () => {
  it('is low when nothing is past 30 days', () => {
    expect(riskOf(party({ buckets: { not_due: 50_00, d1_30: 50_00, d31_60: 0, d61_90: 0, d90_plus: 0 } }))).toBe('low')
  })
  it('is medium with any balance past 30 days but under half past 60', () => {
    expect(riskOf(party({ buckets: { not_due: 0, d1_30: 0, d31_60: 1_00, d61_90: 49_00, d90_plus: 0 } }))).toBe('medium')
  })
  it('is high when more than half of the balance is past 60 days', () => {
    expect(riskOf(party({ buckets: { not_due: 0, d1_30: 0, d31_60: 49_00, d61_90: 1_00, d90_plus: 50_00 } }))).toBe('high')
  })
  it('does not treat exactly half past 60 days as high', () => {
    expect(riskOf(party({ buckets: { not_due: 0, d1_30: 0, d31_60: 50_00, d61_90: 0, d90_plus: 50_00 } }))).toBe('medium')
  })
  it('is high with more than one dispute even if the balance is recent', () => {
    expect(riskOf(party({ disputes: 2 }))).toBe('high')
    expect(riskOf(party({ disputes: 1 }))).toBe('low')
  })
  it('survives a party with no open balance', () => {
    expect(riskOf(party({ openEur: 0, buckets: { not_due: 0, d1_30: 0, d31_60: 0, d61_90: 0, d90_plus: 0 } }))).toBe('low')
  })
})

describe('filterParties', () => {
  const rows = [party({ partyId: 'C1', partyName: 'Acme Ibérica' }), party({ partyId: 'C2', partyName: 'Búho SL', entity: 'DE01' })]
  it('returns everything without a query', () => {
    expect(filterParties(rows, null)).toHaveLength(2)
  })
  it('matches name, id or entity ignoring case and accents', () => {
    expect(filterParties(rows, 'buho').map((p) => p.partyId)).toEqual(['C2'])
    expect(filterParties(rows, 'c1').map((p) => p.partyId)).toEqual(['C1'])
    expect(filterParties(rows, 'de01').map((p) => p.partyId)).toEqual(['C2'])
  })
})

describe('sort in the URL', () => {
  it('round-trips known columns and ignores unknown ones', () => {
    expect(sortFromParam('-overdueEur')).toEqual({ columnId: 'overdueEur', direction: 'desc' })
    expect(sortToParam({ columnId: 'partyName', direction: 'asc' })).toBe('partyName')
    expect(sortFromParam('nope')).toBeNull()
  })
})
