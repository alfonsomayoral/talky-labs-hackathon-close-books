import { describe, expect, it } from 'vitest'
import { categoryLabel, partyHowLabel, ruleDescription } from './labels'

describe('categoryLabel', () => {
  it('names a category of the master in Spanish', () => {
    expect(categoryLabel('BANK_FEES')).toBe('Comisiones bancarias')
    expect(categoryLabel('CASH_POOL')).toBe('Cash pooling')
  })

  it('keeps an unknown category readable as its code', () => {
    expect(categoryLabel('NEW_FINAL_CATEGORY')).toBe('NEW_FINAL_CATEGORY')
  })
})

describe('ruleDescription', () => {
  it('explains a known rule', () => {
    expect(ruleDescription('FILE-DD-BATCH')).toBe('Remesa de recibos: el fichero dice qué facturas cobra')
  })
  it('falls back to the family for a rule it does not know yet, since FINAL may bring more', () => {
    expect(ruleDescription('ADVICE-JSON')).toBe('Aviso de remesa: el documento del cliente dice qué paga')
    expect(ruleDescription('PARTY-NEW')).toBe('Tercero e importe: sin referencia, cuadra con sus partidas abiertas')
  })
  it('gives nothing for something unknown, rather than making it up', () => {
    expect(ruleDescription('OTHER')).toBeUndefined()
  })
})

describe('partyHowLabel', () => {
  it('names how the party was found, and keeps an unknown value readable', () => {
    expect(partyHowLabel('iban')).toBe('Por el IBAN del ordenante')
    expect(partyHowLabel('nuevo')).toBe('nuevo')
  })
  it('explains a rule when the API sends the rule as the way it was found', () => {
    expect(partyHowLabel('ADVICE-TXT')).toBe('Aviso de remesa: el documento del cliente dice qué paga')
  })
})
