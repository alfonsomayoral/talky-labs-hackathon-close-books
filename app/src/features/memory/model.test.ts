import { describe, expect, it } from 'vitest'
import type { MemoryRule } from '@/domain'
import { cleanParams, describeRule, keyParams, rulesInScope, runCommand, validateDescription, validateParams } from './model'

describe('rulesInScope', () => {
  const r = (ruleId: string, scope: MemoryRule['scope']) => ({ ruleId, scope }) as MemoryRule
  const rules = [r('A', { entity: 'ES01' }), r('B', {}), r('C', { entity: 'PT01' })]
  it('keeps the entity rules and the group rules, or everything with no scope', () => {
    expect(rulesInScope(rules, 'ES01').map((x) => x.ruleId)).toEqual(['A', 'B'])
    expect(rulesInScope(rules, null)).toHaveLength(3)
  })
})

describe('cleanParams', () => {
  it('trims, drops empty fields and normalises the IBAN', () => {
    expect(
      cleanParams({
        partyId: ' CES01000001 ',
        payerName: '   ',
        iban: 'es91 2100 0418 4502 0005 1332',
      }),
    ).toEqual({
      partyId: 'CES01000001',
      iban: 'ES9121000418450200051332',
    })
  })
})

describe('validateParams', () => {
  it('payer_is_customer needs the customer and the payer name or the IBAN', () => {
    expect(validateParams('payer_is_customer', {})).toEqual({
      partyId: expect.any(String),
      payerName: expect.any(String),
    })
    expect(validateParams('payer_is_customer', { partyId: 'C1', payerName: 'ACME' })).toEqual({})
    expect(
      validateParams('payer_is_customer', {
        partyId: 'C1',
        iban: 'ES9121000418450200051332',
      }),
    ).toEqual({})
  })
  it('rejects an IBAN that cannot be one', () => {
    expect(validateParams('payer_is_customer', { partyId: 'C1', iban: '1234' })).toHaveProperty('iban')
  })
  it('reference_alias needs the pattern and a document or a party', () => {
    expect(Object.keys(validateParams('reference_alias', { pattern: 'REF 1' }))).toEqual(['documentNumber'])
    expect(
      validateParams('reference_alias', {
        pattern: 'REF 1',
        documentNumber: 'FV-1',
      }),
    ).toEqual({})
    expect(validateParams('reference_alias', { documentNumber: 'FV-1' })).toHaveProperty('pattern')
  })
  it('always_category needs a category in capitals and something to recognise the movement by', () => {
    expect(Object.keys(validateParams('always_category', { bank: 'B1' })).sort()).toEqual(['category', 'textPattern'])
    expect(
      validateParams('always_category', {
        category: 'bank fees',
        textPattern: 'COM',
      }),
    ).toHaveProperty('category')
    expect(
      validateParams('always_category', {
        category: 'BANK_FEES',
        bankCode: '0123',
      }),
    ).toEqual({})
  })
  it('ignore_suffix needs a regex that compiles', () => {
    expect(validateParams('ignore_suffix', { partyId: 'S1', regex: '(' })).toHaveProperty('regex')
    expect(validateParams('ignore_suffix', { partyId: 'S1', regex: '-\\d{2}$' })).toEqual({})
  })
  it('parent_pays needs two different parties', () => {
    expect(validateParams('parent_pays', { payerPartyId: 'C1', forPartyId: 'C1' })).toHaveProperty('forPartyId')
    expect(validateParams('parent_pays', { payerPartyId: 'C1', forPartyId: 'C2' })).toEqual({})
  })
  it('supplier_nets_credit_notes only needs the supplier', () => {
    expect(validateParams('supplier_nets_credit_notes', {})).toHaveProperty('partyId')
    expect(validateParams('supplier_nets_credit_notes', { partyId: 'S1' })).toEqual({})
  })
})

describe('describeRule', () => {
  it('names the payer by name, falling back to the IBAN', () => {
    expect(
      describeRule('payer_is_customer', {
        partyId: 'C1',
        payerName: 'ACME SL',
      }),
    ).toBe('«ACME SL» es un pago del cliente C1.')
    expect(describeRule('payer_is_customer', { partyId: 'C1', iban: 'ES91' })).toBe('El IBAN ES91 es un pago del cliente C1.')
  })
  it('only mentions the bank filters that were filled in', () => {
    expect(
      describeRule('always_category', {
        category: 'BANK_FEES',
        textPattern: 'COMISION',
      }),
    ).toBe('Los movimientos con «COMISION» van siempre a BANK_FEES.')
    expect(
      describeRule('always_category', {
        category: 'BANK_FEES',
        bank: 'B1',
        bankCode: '12',
        bankSubcode: '3',
      }),
    ).toBe('Los movimientos del banco B1, código 12/3 van siempre a BANK_FEES.')
  })
  it('prefers the document to the party for an alias', () => {
    expect(
      describeRule('reference_alias', {
        pattern: 'R1',
        documentNumber: 'FV-9',
        partyId: 'C1',
      }),
    ).toBe('La referencia «R1» corresponde a la factura FV-9.')
    expect(describeRule('reference_alias', { pattern: 'R1', partyId: 'C1' })).toBe('La referencia «R1» corresponde al tercero C1.')
  })
})

describe('validateDescription', () => {
  it('must say something, within a line', () => {
    expect(validateDescription('  ')).not.toBeNull()
    expect(validateDescription('x'.repeat(301))).not.toBeNull()
    expect(validateDescription('Una regla')).toBeNull()
  })
})

describe('keyParams', () => {
  const rule = (params: MemoryRule['params']): MemoryRule => ({
    ruleId: 'MR-0001',
    kind: 'parent_pays',
    params,
    description: '',
    scope: {},
    createdFrom: {},
    by: '',
    at: '',
    active: true, affectedTxns: 0,
  })
  it('lists the params in the order of the form, with their labels, skipping what is empty or unknown', () => {
    expect(keyParams(rule({ forPartyId: 'C2', payerPartyId: 'C1', extra: 'x', empty: '' }))).toEqual([
      { label: 'Paga', value: 'C1' },
      { label: 'Por cuenta de', value: 'C2' },
    ])
  })
})

describe('runCommand', () => {
  it('points at the human folder of the run', () => {
    expect(runCommand('live-1')).toBe('closebooks run --memory runs/live-1/human/')
  })
})
