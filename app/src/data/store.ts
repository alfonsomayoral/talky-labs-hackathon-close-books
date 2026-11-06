// Loaded package, run and their links. Phase 0 keeps nothing between reloads (ARCHITECTURE.md §4.3).
import { create } from 'zustand'
import type { Dataset, Run } from '@/domain'
import { buildDataset } from './build'
import { SAMPLE_NAME, SAMPLE_PERIOD, samplePackage } from './fixtures/sample'
import { buildLinks, type Links } from './links'
import { importZip } from './sources/importZip'

export interface DataState {
  status: 'loading' | 'ready' | 'error'
  dataset: Dataset | null
  run: Run | null
  links: Links | null
  error: string | null
  loadSample: () => void
  importZip: (file: File) => Promise<void>
}

const ready = (dataset: Dataset, run: Run | null) => ({ status: 'ready' as const, dataset, run, links: buildLinks(dataset, run), error: null })

export const useData = create<DataState>()((set) => ({
  status: 'loading',
  dataset: null,
  run: null,
  links: null,
  error: null,
  loadSample: () => {
    const { files, run } = samplePackage()
    set(ready(buildDataset(files, { name: SAMPLE_NAME, period: SAMPLE_PERIOD, source: 'fixtures', loadedAt: new Date().toISOString() }), run))
  },
  importZip: async (file) => {
    set({ status: 'loading', error: null })
    try {
      set(ready(await importZip(file), null))
    } catch (e) {
      // A failed import keeps the data already loaded.
      set((s) => ({ status: s.dataset ? 'ready' : 'error', error: e instanceof Error ? e.message : String(e) }))
    }
  },
}))

useData.getState().loadSample()
