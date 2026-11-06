import { decimalToCents } from './text'
import { parseCsv, parseJsonRows, parseJsonl, parseTabular } from './tabular'

describe('parseCsv', () => {
  it('reads a header row and quoted cells with commas', () => {
    expect(parseCsv('id,name\r\nV1,"Acme, S.L."\n')).toEqual([{ id: 'V1', name: 'Acme, S.L.' }])
  })

  it('detects the semicolon separator of Spanish exports', () => {
    expect(parseCsv('id;importe\nF1;1.234,56')).toEqual([{ id: 'F1', importe: '1.234,56' }])
  })
})

describe('parseJsonl', () => {
  it('skips blank lines and names the bad line', () => {
    expect(parseJsonl('{"a":1}\n\n{"a":2}')).toEqual([{ a: 1 }, { a: 2 }])
    expect(() => parseJsonl('{"a":1}\n{oops')).toThrow(/línea 2/)
  })
})

describe('parseJsonRows', () => {
  it('accepts an array or an object wrapping one array', () => {
    expect(parseJsonRows('[{"a":1}]')).toEqual([{ a: 1 }])
    expect(parseJsonRows('{"data":[{"a":1}],"meta":{}}')).toEqual([{ a: 1 }])
    expect(parseJsonRows('{"a":1}')).toBeNull()
  })
})

it('parseTabular returns null for non-tabular files', () => {
  expect(parseTabular('docs/invoice.pdf', '%PDF')).toBeNull()
})

describe('decimalToCents', () => {
  it.each([
    ['1234.56', 123456],
    ['1.234,56', 123456],
    ['1,234.56', 123456],
    ['-0,5', -50],
    ['abc', Number.NaN],
  ])('%s → %s', (input, cents) => {
    expect(decimalToCents(input)).toBe(cents)
  })
})
