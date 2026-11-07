import { describe, expect, it } from 'vitest'
import { ageDays, ageLabel, sortFromParam, sortToParam } from './model'

describe('sort in the URL', () => {
  it('reads an allowed field, ascending or descending', () => {
    expect(sortFromParam('priority')).toEqual({ columnId: 'priority', direction: 'asc' })
    expect(sortFromParam('-amountEur')).toEqual({ columnId: 'amountEur', direction: 'desc' })
  })

  it('ignores fields the list does not sort by', () => {
    expect(sortFromParam('summary')).toBeNull()
    expect(sortFromParam(null)).toBeNull()
  })

  it('writes the API form back, and nothing when unsorted', () => {
    expect(sortToParam({ columnId: 'bookingDate', direction: 'desc' })).toBe('-bookingDate')
    expect(sortToParam({ columnId: 'bookingDate', direction: 'asc' })).toBe('bookingDate')
    expect(sortToParam(null)).toBeNull()
  })
})

describe('age', () => {
  it('counts whole days between the booking date and the reference date', () => {
    expect(ageDays('2025-11-01', '2025-11-08')).toBe(7)
    expect(ageDays('2025-11-08', '2025-11-08')).toBe(0)
  })

  it('is null without a date, and never negative', () => {
    expect(ageDays(null, '2025-11-08')).toBeNull()
    expect(ageDays('2025-12-01', '2025-11-08')).toBe(0)
  })

  it('reads days up to two months, then months', () => {
    expect(ageLabel(0)).toBe('0 d')
    expect(ageLabel(1)).toBe('1 d')
    expect(ageLabel(45)).toBe('45 d')
    expect(ageLabel(75)).toBe('3 meses')
    expect(ageLabel(null)).toBe('—')
  })
})
