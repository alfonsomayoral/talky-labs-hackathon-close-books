import { describe, expect, it } from 'vitest'
import { CASE_KIND_LABEL } from './labels'
import type { CaseKind } from './run'
import { QUEUES, firstActionable, queueFilter, queueOfKind } from './queues'

const inQueue = (id: 'revisar' | 'reclamar') => queueFilter(id).kind!.split(',')

describe('queues', () => {
  it('leaves questions out of the kind queues, so no case counts twice', () => {
    expect(queueFilter('decidir')).toEqual({ status: 'question' })
    expect(queueFilter('revisar').status).toBe('needs_review,fallback')
    expect(queueFilter('reclamar').status).toBe('needs_review,fallback')
  })

  it('gives every kind exactly one queue', () => {
    const kinds = Object.keys(CASE_KIND_LABEL).sort()
    expect([...inQueue('revisar'), ...inQueue('reclamar')].sort()).toEqual(kinds)
  })

  it('reviews what has no match and claims what has an open balance', () => {
    const of = (kinds: CaseKind[]) => kinds.map(queueOfKind)
    expect(of(['unidentified_receipt', 'ambiguous_match', 'unknown_debit', 'fx_difference'])).toEqual(['revisar', 'revisar', 'revisar', 'revisar'])
    expect(of(['short_payment', 'dispute', 'overdue_customer', 'overpayment'])).toEqual(['reclamar', 'reclamar', 'reclamar', 'reclamar'])
  })

  it('has a different primary action in each queue', () => {
    expect(new Set(QUEUES.map((q) => q.primary)).size).toBe(QUEUES.length)
  })
})

describe('firstActionable', () => {
  const rows = [
    { caseId: 'a', suggestedAction: 'review' },
    { caseId: 'b', suggestedAction: 'email_customer' },
  ] as const

  it('takes the first case of the sorted list', () => {
    expect(firstActionable('revisar', rows)?.caseId).toBe('a')
  })

  it('skips cases with no email template when the action is to write', () => {
    expect(firstActionable('reclamar', rows)?.caseId).toBe('b')
    expect(firstActionable('reclamar', [rows[0]])).toBeUndefined()
  })
})
