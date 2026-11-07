import { describe, expect, it } from 'vitest'
import { primaryAction, recipientLine } from './model'

describe('primaryAction', () => {
  const base = { status: 'needs_review' as const, suggestedAction: 'review' as const, question: null, draft: null }

  it('answers an open question', () => {
    const question = { status: 'open' as const }
    expect(primaryAction({ ...base, status: 'question', suggestedAction: 'ask', question })).toBe('answer')
  })

  it('reviews the draft of an email case', () => {
    expect(primaryAction({ ...base, suggestedAction: 'email_supplier', draft: { status: 'draft' } })).toBe('email')
  })

  it('offers to prepare the email when the case has no draft yet', () => {
    expect(primaryAction({ ...base, suggestedAction: 'email_customer' })).toBe('prepare_email')
  })

  it('moves on to marking it handled once the email is sent or taken manually', () => {
    expect(primaryAction({ ...base, suggestedAction: 'email_customer', draft: { status: 'sent' } })).toBe('done')
    expect(primaryAction({ ...base, suggestedAction: 'email_customer', draft: { status: 'manual' } })).toBe('done')
  })

  it('has nothing to ask when the question is missing or already answered', () => {
    expect(primaryAction({ ...base, suggestedAction: 'ask' })).toBe('done')
    expect(primaryAction({ ...base, suggestedAction: 'ask', question: { status: 'answered' } })).toBe('done')
  })

  it('only offers marking handled for plain review cases', () => {
    expect(primaryAction(base)).toBe('done')
  })

  it('has no action for a case somebody already closed', () => {
    expect(primaryAction({ ...base, status: 'done' })).toBe('closed')
  })
})

describe('recipientLine', () => {
  it('gives name and address', () => {
    expect(recipientLine({ toName: 'Navarro GmbH', to: 'pagos@navarro.example' })).toBe('Navarro GmbH <pagos@navarro.example>')
  })
  it('never prints a missing address: the masters carry no emails', () => {
    expect(recipientLine({ toName: 'Navarro GmbH', to: null })).toBe('Navarro GmbH')
    expect(recipientLine({ toName: null, to: null })).toBe('')
  })
})
