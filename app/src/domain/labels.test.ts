import { describe, expect, it } from 'vitest'
import { categoryLabel } from './labels'

describe('categoryLabel', () => {
  it('names a category of the master in Spanish', () => {
    expect(categoryLabel('BANK_FEES')).toBe('Comisiones bancarias')
    expect(categoryLabel('CASH_POOL')).toBe('Cash pooling')
  })

  it('keeps an unknown category readable as its code', () => {
    expect(categoryLabel('NEW_FINAL_CATEGORY')).toBe('NEW_FINAL_CATEGORY')
  })
})
