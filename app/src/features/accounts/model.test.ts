import { describe, expect, it } from 'vitest'
import type { Account } from '@/domain'
import { currentFormat, filterByEntity, formatChange, summarize } from './model'

const account = (over: Partial<Account>): Account => ({
  accountId: 'ES00-001',
  entity: 'ES00',
  bank: 'SAB',
  bankName: null,
  currency: 'EUR',
  iban: null,
  purpose: null,
  inMaster: true,
  formats: [{ format: 'n43', from: '2025-07-01', to: null }],
  txns: 0,
  inflowCents: 0,
  outflowCents: 0,
  netCents: 0,
  firstDate: null,
  lastDate: null,
  reconciledRate: null,
  ...over,
})

describe('formatChange', () => {
  it('is null while the format never changed', () => {
    expect(formatChange(account({}).formats)).toBeNull()
  })

  it('names the old and the new format and when the new one starts', () => {
    const formats = [
      { format: 'camt053', from: '2025-10-01', to: null },
      { format: 'n43', from: '2025-07-01', to: '2025-09-30' },
    ]
    expect(formatChange(formats)).toBe('n43 → camt053 desde oct 2025')
  })

  it('chains several changes and reports the last start', () => {
    const formats = [
      { format: 'n43', from: '2025-07-01', to: '2025-08-31' },
      { format: 'mt940', from: '2025-09-01', to: '2025-11-30' },
      { format: 'camt053', from: '2025-12-01', to: null },
    ]
    expect(formatChange(formats)).toBe('n43 → mt940 → camt053 desde dic 2025')
  })

  it('does not call a change two periods of the same format', () => {
    const formats = [
      { format: 'n43', from: '2025-07-01', to: '2025-09-30' },
      { format: 'n43', from: '2025-10-01', to: null },
    ]
    expect(formatChange(formats)).toBeNull()
  })
})

describe('currentFormat', () => {
  it('is the format of the open period, not of the first one', () => {
    const formats = [
      { format: 'camt053', from: '2025-10-01', to: null },
      { format: 'n43', from: '2025-07-01', to: '2025-09-30' },
    ]
    expect(currentFormat(formats)).toBe('camt053')
  })

  it('is null with no periods', () => {
    expect(currentFormat([])).toBeNull()
  })
})

describe('summarize', () => {
  it('counts accounts, distinct banks and accounts that changed format', () => {
    const changed = [
      { format: 'n43', from: '2025-07-01', to: '2025-09-30' },
      { format: 'camt053', from: '2025-10-01', to: null },
    ]
    const accounts = [
      account({ accountId: 'a', bank: 'SAB' }),
      account({ accountId: 'b', bank: 'SAB', formats: changed }),
      account({ accountId: 'c', bank: 'BBV', formats: changed }),
    ]
    expect(summarize(accounts)).toEqual({ accounts: 3, banks: 2, formatChanges: 2 })
  })
})

describe('filterByEntity', () => {
  const accounts = [account({ accountId: 'a', entity: 'ES00' }), account({ accountId: 'b', entity: 'MX01' })]

  it('keeps the whole group with no scope', () => {
    expect(filterByEntity(accounts, null)).toHaveLength(2)
  })

  it('keeps only the accounts of the entity', () => {
    expect(filterByEntity(accounts, 'MX01').map((a) => a.accountId)).toEqual(['b'])
  })
})
