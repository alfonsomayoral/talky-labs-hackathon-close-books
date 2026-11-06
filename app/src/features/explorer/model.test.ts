import { describe, expect, it } from 'vitest'
import type { DocumentFact } from '@/domain'
import { factExtras, fromSortParam, switchTab, toSortParam, withParams } from './model'

describe('sort in the URL', () => {
  it('writes the column as the API wants it: field, or -field when descending', () => {
    expect(toSortParam({ columnId: 'totalCents', direction: 'asc' })).toBe('totalCents')
    expect(toSortParam({ columnId: 'totalCents', direction: 'desc' })).toBe('-totalCents')
    expect(toSortParam(null)).toBeNull()
  })

  it('reads it back', () => {
    expect(fromSortParam('-dueDate')).toEqual({ columnId: 'dueDate', direction: 'desc' })
    expect(fromSortParam('dueDate')).toEqual({ columnId: 'dueDate', direction: 'asc' })
    expect(fromSortParam(null)).toBeNull()
    expect(fromSortParam('-')).toBeNull()
  })
})

describe('switchTab', () => {
  it('keeps the run and the entity and drops what belongs to the old tab', () => {
    const params = new URLSearchParams('run=live-1&sociedad=ES01&tipo=items&q=abc&filtro=ARI&orden=-dueDate&ver=API1')
    expect(switchTab(params, 'parties').toString()).toBe('run=live-1&sociedad=ES01&tipo=parties')
  })

  it('works with no run and no entity', () => {
    expect(switchTab(new URLSearchParams('q=x'), 'documents').toString()).toBe('tipo=documents')
  })
})

describe('withParams', () => {
  it('adds params to the scoped link without losing the run and the entity', () => {
    const link = withParams({ pathname: '/conciliacion', search: '?run=live-1&sociedad=ES01' }, { ver: 'BT-1' })
    expect(link).toEqual({ pathname: '/conciliacion', search: '?run=live-1&sociedad=ES01&ver=BT-1' })
  })

  it('works on a link with no search', () => {
    expect(withParams({ pathname: '/bandeja', search: '' }, { ver: 'CASE-9' })).toEqual({ pathname: '/bandeja', search: '?ver=CASE-9' })
  })

  it('encodes values', () => {
    expect(withParams({ pathname: '/explorador', search: '' }, { ver: 'a b/c.pdf' }).search).toBe('?ver=a+b%2Fc.pdf')
  })
})

describe('factExtras', () => {
  const fact = (over: Partial<DocumentFact>): DocumentFact => ({
    lineNo: 1,
    documentNumber: 'ARI0001',
    documentNumberNorm: 'ARI0001',
    grossCents: null,
    deductionCents: null,
    reason: null,
    paidCents: null,
    currency: null,
    customerPo: null,
    voucher: null,
    clause: null,
    clauseValue: null,
    method: 'parser',
    model: null,
    ...over,
  })

  it('lists only what the document carries, labelled', () => {
    expect(factExtras(fact({ customerPo: 'PO-77', voucher: 'V-3' }))).toEqual(['Pedido PO-77', 'Voucher V-3'])
  })

  it('is empty when there is nothing extra', () => {
    expect(factExtras(fact({}))).toEqual([])
  })

  it('includes the clause with its value', () => {
    expect(factExtras(fact({ clause: 'early_discount', clauseValue: { pct: 2 } }))).toEqual(['Cláusula early_discount {"pct":2}'])
  })
})
