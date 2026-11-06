// Unzips and maps the client's package off the main thread: the ledger can be large.
import { buildDataset } from '../build'
import { readZip } from './zip'

export interface ImportRequest {
  bytes: ArrayBuffer
  name: string
  loadedAt: string
}

self.onmessage = (e: MessageEvent<ImportRequest>) => {
  const { bytes, name, loadedAt } = e.data
  try {
    const dataset = buildDataset(readZip(new Uint8Array(bytes)), { name, period: null, source: 'zip', loadedAt })
    self.postMessage({ ok: true, dataset })
  } catch (err) {
    self.postMessage({ ok: false, error: err instanceof Error ? err.message : String(err) })
  }
}
