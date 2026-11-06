import { describe, expect, it } from 'vitest'
import type { Account, RunStats, TxnRow } from '@/domain'
import { buildFacetOptions, hasActiveFilters, rowsCell, sortFromParam, sortToParam, toApiParams } from './model'

const none = { account: [], rule: [], exception: [], category: [], status: [], entity: [], format: [] }

describe('toApiParams', () => {
  it('joins multi-value facets with commas and leaves empty ones out', () => {
    const p = toApiParams({ q: 'alba', entity: null, facets: { ...none, rule: ['ADVICE-TXT', 'REF-EXACT'], status: ['fallback'] }, sort: null })
    expect(p).toMatchObject({ q: 'alba', rule: 'ADVICE-TXT,REF-EXACT', caseStatus: 'fallback' })
    expect(p).not.toHaveProperty('exception')
    expect(p.entity).toBeUndefined()
  })

  it('the shell scope wins over the entity facet', () => {
    const p = toApiParams({ q: '', entity: 'ES01', facets: { ...none, entity: ['ES02', 'ES03'] }, sort: null })
    expect(p.entity).toBe('ES01')
  })

  it('uses the entity facet when there is no scope, and trims the search', () => {
    const p = toApiParams({ q: '  mes  ', entity: null, facets: { ...none, entity: ['ES02', 'ES03'], account: ['4009'] }, sort: null })
    expect(p).toMatchObject({ q: 'mes', entity: 'ES02,ES03', accountId: '4009' })
  })
})

describe('sort in the URL', () => {
  it('round-trips ascending and descending', () => {
    expect(sortToParam({ columnId: 'bookingDate', direction: 'desc' })).toBe('-bookingDate')
    expect(sortToParam({ columnId: 'rule', direction: 'asc' })).toBe('rule')
    expect(sortToParam(null)).toBeNull()
    expect(sortFromParam('-amountEur')).toEqual({ columnId: 'amountEur', direction: 'desc' })
    expect(sortFromParam('rule')).toEqual({ columnId: 'rule', direction: 'asc' })
    expect(sortFromParam(null)).toBeNull()
    expect(sortFromParam('-')).toBeNull()
  })

  it('reaches the API as the sort param', () => {
    expect(toApiParams({ q: '', entity: null, facets: none, sort: { columnId: 'confidence', direction: 'desc' } }).sort).toBe('-confidence')
  })
})

describe('hasActiveFilters', () => {
  it('is true for a search or any facet', () => {
    expect(hasActiveFilters({ q: '', facets: none })).toBe(false)
    expect(hasActiveFilters({ q: 'x', facets: none })).toBe(true)
    expect(hasActiveFilters({ q: '', facets: { ...none, category: ['BANK_FEE'] } })).toBe(true)
  })
})

describe('rowsCell', () => {
  const base = { assignments: [] } as unknown as TxnRow
  it('shows the first printed number and how many more rows there are', () => {
    const row = { ...base, rowCount: 4, assignments: [{ documentNumber: 'F-100', category: null, exception: null }] } as unknown as TxnRow
    expect(rowsCell(row)).toEqual({ first: 'F-100', mono: true, extra: 3 })
  })
  it('falls back to the exception or category label when the row has no item', () => {
    const exc = { ...base, rowCount: 1, assignments: [{ documentNumber: null, category: null, exception: 'UNIDENTIFIED' }] } as unknown as TxnRow
    expect(rowsCell(exc)).toEqual({ first: 'Sin identificar', mono: false, extra: 0 })
    const cat = { ...base, rowCount: 1, assignments: [{ documentNumber: null, category: 'BANK_FEE', exception: null }] } as unknown as TxnRow
    expect(rowsCell(cat)).toEqual({ first: 'BANK_FEE', mono: false, extra: 0 })
    const known = { ...base, rowCount: 1, assignments: [{ documentNumber: null, category: 'BANK_FEES', exception: null }] } as unknown as TxnRow
    expect(rowsCell(known)).toEqual({ first: 'Comisiones bancarias', mono: false, extra: 0 })
  })
  it('has nothing when the movement has no rows', () => {
    expect(rowsCell({ ...base, rowCount: 0 } as TxnRow)).toEqual({ first: null, mono: false, extra: 0 })
  })
})

describe('buildFacetOptions', () => {
  const stats = {
    byEntity: [{ entity: 'ES01', name: 'Valtermia España', txns: 50 }],
    byRule: [{ rule: 'ADVICE-TXT', rows: 90, txns: 40 }],
    byException: [{ exception: 'PARTIAL', rows: 3, amountEur: 1 }],
    byCategory: [{ category: 'BANK_FEE', txns: 7, amountEur: 1 }],
    byStatus: { fallback: 9, needs_review: 4 },
  } as unknown as RunStats
  const accounts = [
    { accountId: '4009', entity: 'ES01', bank: 'BBVA', txns: 30, formats: [] },
    { accountId: '4010', entity: 'ES02', bank: 'SAN', txns: 20, formats: [] },
  ] as unknown as Account[]

  it('reads every option from the run, with its label and count', () => {
    const o = buildFacetOptions(stats, accounts, null)
    expect(o.entity).toEqual([{ value: 'ES01', label: 'ES01 · Valtermia España', count: 50 }])
    expect(o.rule).toEqual([{ value: 'ADVICE-TXT', label: 'ADVICE-TXT', count: 40 }])
    expect(o.exception).toEqual([{ value: 'PARTIAL', label: 'Pago parcial' }])
    expect(o.category).toEqual([{ value: 'BANK_FEE', label: 'BANK_FEE', count: 7 }])
    expect(o.status).toEqual([
      { value: 'needs_review', label: 'Por revisar', count: 4 },
      { value: 'fallback', label: 'Sin casación', count: 9 },
    ])
    expect(o.account).toHaveLength(2)
  })

  it('limits accounts to the entity in scope', () => {
    expect(buildFacetOptions(stats, accounts, 'ES02').account.map((a) => a.value)).toEqual(['4010'])
  })

  it('is empty while the data has not arrived', () => {
    const o = buildFacetOptions(undefined, undefined, null)
    expect(Object.values(o).every((l) => l.length === 0)).toBe(true)
  })
})

describe('format facet', () => {
  const account = (accountId: string, formats: string[], entity = 'ES01') => ({ accountId, entity, bank: 'X', txns: 1, formats: formats.map((format) => ({ format })) }) as unknown as Account

  it('offers every statement format of the accounts, once, including the one they change to', () => {
    const options = buildFacetOptions(undefined, [account('A', ['n43', 'camt053']), account('B', ['camt053']), account('C', ['mt940'])], null)
    expect(options.format.map((o) => o.value)).toEqual(['camt053', 'mt940', 'n43'])
  })

  it('goes to the API as statementFormat', () => {
    const p = toApiParams({ q: '', entity: null, facets: { ...none, format: ['n43', 'mt940'] }, sort: null })
    expect(p.statementFormat).toBe('n43,mt940')
  })
})
