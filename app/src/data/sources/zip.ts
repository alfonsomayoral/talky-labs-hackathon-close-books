// The client's zip → package files. Tabular files are decoded to text; the rest stay binary (text null).
import { unzipSync } from 'fflate'
import type { PackageFile } from '../build'
import { decodeText } from '../parsers/text'

const TEXT = /\.(csv|jsonl|ndjson|json|txt|md|xml)$/i
const JUNK = /(^|\/)(__MACOSX\/|\.DS_Store$)/

export function readZip(bytes: Uint8Array): PackageFile[] {
  const entries = unzipSync(bytes, { filter: (f) => !f.name.endsWith('/') && !JUNK.test(f.name) })
  return Object.entries(entries).map(([path, data]) => ({ path, size: data.length, text: TEXT.test(path) ? decodeText(data) : null }))
}
