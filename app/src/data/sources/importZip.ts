import type { Dataset } from '@/domain'
import type { ImportRequest } from './import.worker'

export function importZip(file: File): Promise<Dataset> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL('./import.worker.ts', import.meta.url), { type: 'module' })
    worker.onmessage = (e: MessageEvent<{ ok: true; dataset: Dataset } | { ok: false; error: string }>) => {
      worker.terminate()
      if (e.data.ok) resolve(e.data.dataset)
      else reject(new Error(e.data.error))
    }
    worker.onerror = (e) => {
      worker.terminate()
      reject(new Error(e.message || 'No se pudo leer el zip'))
    }
    void file.arrayBuffer().then((bytes) => {
      const req: ImportRequest = { bytes, name: file.name.replace(/\.zip$/i, ''), loadedAt: new Date().toISOString() }
      worker.postMessage(req, [bytes])
    }, reject)
  })
}
