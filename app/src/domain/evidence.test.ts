import { describe, expect, it } from 'vitest'
import { evidenceOf } from './evidence'

describe('evidenceOf', () => {
  it('names the source of each family of rules', () => {
    const source = (rule: string) => evidenceOf(rule).source
    expect(source('ADVICE-CSV')).toBe('Aviso de remesa')
    expect(source('ADVICE-PDF')).toBe('PDF')
    expect(source('PARTY-PLAN')).toBe('PDF')
    expect(source('FILE-PAYMENT-RUN')).toBe('Remesa de pagos')
    expect(source('FILE-DD-RETURN')).toBe('Recibos')
    expect(source('FILE-CARD-CHARGEBACK')).toBe('Tarjeta')
    expect(source('FILE-CHEQUE')).toBe('Cheque')
    expect(source('PARTY-AMOUNT')).toBe('Maestro')
    expect(source('MEMORY-RULE')).toBe('Memoria')
  })

  it('tells documents from party and amount, and both from the fallback', () => {
    const group = (rule: string) => evidenceOf(rule).group
    expect(['ADVICE-XLSX', 'FILE-CARD', 'REF-TEXT', 'PARTY-PLAN'].map(group)).toEqual(['document', 'document', 'document', 'document'])
    expect(group('PARTY-SUBSET')).toBe('party')
    expect(group('CAT-CODE')).toBe('category')
    expect(group('FALLBACK-UNIDENTIFIED')).toBe('fallback')
  })

  it('backs a payout of a credit note with its reference or PDF, and paired receipts with the other movement', () => {
    expect(evidenceOf('CREDIT-PAYOUT')).toEqual({ source: 'Referencia o PDF', group: 'document' })
    expect(evidenceOf('PAIRED-PARTIAL')).toEqual({ source: 'Otro movimiento', group: 'movement' })
  })

  it('does not call an unknown rule documentary', () => {
    expect(evidenceOf('NEW-THING')).toEqual({ source: 'Otra', group: 'fallback' })
  })
})
