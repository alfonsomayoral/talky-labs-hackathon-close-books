// Any tabular file of the package (CSV, JSON, JSONL) → rows of plain objects. Other formats → null.

export type RawRow = Record<string, unknown>

export function parseCsvLine(line: string, sep: string): string[] {
  const out: string[] = []
  let cur = ''
  let quoted = false
  for (let i = 0; i < line.length; i++) {
    const c = line[i]
    if (quoted) {
      if (c === '"' && line[i + 1] === '"') {
        cur += '"'
        i++
      } else if (c === '"') quoted = false
      else cur += c
    } else if (c === '"') quoted = true
    else if (c === sep) {
      out.push(cur)
      cur = ''
    } else cur += c
  }
  out.push(cur)
  return out
}

/** CSV with a header row. The separator is `;` when the header has more `;` than `,` (Spanish Excel exports). */
export function parseCsv(text: string): RawRow[] {
  const lines = text.split('\n').map((l) => l.replace(/\r$/, '')).filter((l) => l.trim() !== '')
  if (!lines.length) return []
  const count = (ch: string) => lines[0].split(ch).length
  const sep = count(';') > count(',') ? ';' : ','
  const header = parseCsvLine(lines[0], sep).map((h) => h.trim())
  return lines.slice(1).map((line) => {
    const cells = parseCsvLine(line, sep)
    return Object.fromEntries(header.map((h, i) => [h, cells[i] ?? '']))
  })
}

export function parseJsonl(text: string): RawRow[] {
  const out: RawRow[] = []
  text.split('\n').forEach((raw, i) => {
    const line = raw.replace(/\r$/, '')
    if (!line.trim()) return
    try {
      out.push(JSON.parse(line) as RawRow)
    } catch (e) {
      throw new Error(`JSON inválido en la línea ${i + 1}: ${e instanceof Error ? e.message : String(e)}`)
    }
  })
  return out
}

/** A JSON array of objects, or an object whose only array property holds the rows (`{ "data": [...] }`). */
export function parseJsonRows(text: string): RawRow[] | null {
  const value: unknown = JSON.parse(text)
  if (Array.isArray(value)) return value as RawRow[]
  if (value && typeof value === 'object') {
    const arrays = Object.values(value).filter(Array.isArray)
    if (arrays.length === 1) return arrays[0] as RawRow[]
  }
  return null
}

export function parseTabular(path: string, text: string): RawRow[] | null {
  const ext = path.toLowerCase().split('.').pop()
  if (ext === 'csv') return parseCsv(text)
  if (ext === 'jsonl' || ext === 'ndjson') return parseJsonl(text)
  if (ext === 'json') return parseJsonRows(text)
  return null
}
