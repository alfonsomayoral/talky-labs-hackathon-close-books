// Package files → Dataset, through the mappings. Pure: runs in the import worker and in tests.
import type { Dataset, DatasetKind, DatasetMeta, RawFile } from '@/domain'
import { parseTabular } from './parsers/tabular'
import { MAPPINGS } from './registry/mappings'

export interface PackageFile {
  path: string
  size: number
  /** Decoded text; null for binary files (PDF, images). */
  text: string | null
}

const PREVIEW_ROWS = 50

export function emptyDataset(meta: DatasetMeta): Dataset {
  return {
    meta,
    entities: [],
    vendors: [],
    contracts: [],
    purchaseOrders: [],
    invoices: [],
    bankTransactions: [],
    ledgerEntries: [],
    erpEvents: [],
    unmapped: [],
    issues: [],
  }
}

export function buildDataset(files: PackageFile[], meta: DatasetMeta): Dataset {
  const ds = emptyDataset(meta)
  for (const file of files) {
    const mapping = MAPPINGS.find((m) => m.files(file.path))
    let rows: Record<string, unknown>[] | null = null
    try {
      rows = file.text === null ? null : parseTabular(file.path, file.text)
    } catch (e) {
      ds.issues.push({ path: file.path, row: 0, message: e instanceof Error ? e.message : String(e) })
    }
    if (!mapping || !rows) {
      const raw: RawFile = { path: file.path, size: file.size, preview: rows ? rows.slice(0, PREVIEW_ROWS) : null }
      ds.unmapped.push(raw)
      continue
    }
    const target = ds[mapping.kind] as unknown[]
    rows.forEach((row, i) => {
      try {
        target.push(mapping.map(row))
      } catch (e) {
        ds.issues.push({ path: file.path, row: i + 1, message: e instanceof Error ? e.message : String(e) })
      }
    })
  }
  return ds
}

/** Rows per kind, for the inventory. */
export function countByKind(ds: Dataset): Record<DatasetKind, number> {
  return Object.fromEntries(MAPPINGS.map((m) => [m.kind, ds[m.kind].length])) as Record<DatasetKind, number>
}
