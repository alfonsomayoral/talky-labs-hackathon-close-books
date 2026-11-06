import { strToU8, zipSync } from 'fflate'
import { readZip } from './zip'

it('reads tabular entries as text, keeps binaries and drops macOS junk', () => {
  const zip = zipSync({
    'pkg/invoices.csv': strToU8('id\nF1'),
    'pkg/docs/F1.pdf': new Uint8Array([37, 80, 68, 70]),
    '__MACOSX/pkg/._invoices.csv': strToU8('x'),
    'pkg/.DS_Store': strToU8('x'),
  })
  expect(readZip(zip)).toEqual([
    { path: 'pkg/invoices.csv', size: 5, text: 'id\nF1' },
    { path: 'pkg/docs/F1.pdf', size: 4, text: null },
  ])
})
