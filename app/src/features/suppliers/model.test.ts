import { describe, expect, it } from 'vitest'
import type { OpenItem } from '@/domain'
import { agingSegments, emailState, listKinds, listStatuses, orderItems, sortFromParam } from './model'

const item = (itemId: string) => ({ itemId }) as OpenItem

describe('listStatuses', () => {
  it('is the open queue by default and never includes handled cases', () => {
    expect(listStatuses([])).toBe('auto,needs_review,question,fallback')
  })

  it('adds handled cases only when asked for, ignoring states that are not cases to work', () => {
    expect(listStatuses(['done', 'auto'])).toBe('auto,done')
  })
})

describe('listKinds', () => {
  it('never lets a foreign kind widen the list beyond supplier cases', () => {
    expect(listKinds(['overdue_customer'])).toBe('supplier_invoice_mismatch,supplier_credit_pending')
    expect(listKinds(['supplier_credit_pending', 'dispute'])).toBe('supplier_credit_pending')
  })
})

describe('sortFromParam', () => {
  it('reads allowed fields and drops the rest, so a composite default shows no header arrow', () => {
    expect(sortFromParam('-amountEur')).toEqual({ columnId: 'amountEur', direction: 'desc' })
    expect(sortFromParam('priority,-amountEur')).toBeNull()
  })
})

describe('emailState', () => {
  it('says handled before anything else, and a draft only for supplier emails', () => {
    expect(emailState({ status: 'done', draftId: 'D1', suggestedAction: 'email_supplier' })).toBe('closed')
    expect(emailState({ status: 'needs_review', draftId: 'D1', suggestedAction: 'email_supplier' })).toBe('draft')
    expect(emailState({ status: 'needs_review', draftId: null, suggestedAction: 'email_supplier' })).toBe('none')
    expect(emailState({ status: 'needs_review', draftId: 'D1', suggestedAction: 'review' })).toBe('none')
  })
})

describe('orderItems', () => {
  it('puts the case items first and keeps the received order inside each group', () => {
    const ordered = orderItems([item('A'), item('B'), item('C'), item('D')], ['D', 'B'])
    expect(ordered.map((o) => [o.item.itemId, o.inCase])).toEqual([
      ['B', true],
      ['D', true],
      ['A', false],
      ['C', false],
    ])
  })
})

describe('agingSegments', () => {
  it('follows the bucket order and clamps negative balances to zero', () => {
    const segs = agingSegments({ not_due: 5, d1_30: -2, d31_60: 0, d61_90: 1, d90_plus: 9 })
    expect(segs.map((s) => s.value)).toEqual([5, 0, 0, 1, 9])
    expect(segs[0].label).toBe('No vencido')
  })
})
