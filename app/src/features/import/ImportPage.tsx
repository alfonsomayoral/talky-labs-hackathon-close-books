// Import the client's zip, and see what the mappings could not read: unknown files and bad rows.
import { useRef, useState, type DragEvent } from 'react'
import { FileArchive, RotateCcw, Upload } from 'lucide-react'
import { Badge, Button, Card, EmptyState, Mono, Page, PageHeader, Section } from '@/components'
import { countByKind, useData, VIEWS } from '@/data'
import { formatDateTime, formatNumber } from '@/lib/format'
import styles from './ImportPage.module.css'

const kb = (bytes: number) => `${formatNumber(Math.max(1, Math.round(bytes / 1024)))} KB`

export function ImportPage() {
  const dataset = useData((s) => s.dataset)!
  const status = useData((s) => s.status)
  const error = useData((s) => s.error)
  const importZip = useData((s) => s.importZip)
  const loadSample = useData((s) => s.loadSample)
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const counts = countByKind(dataset)

  const take = (files: FileList | null) => {
    const zip = files && [...files].find((f) => /\.zip$/i.test(f.name))
    if (zip) void importZip(zip)
  }
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setOver(false)
    take(e.dataTransfer.files)
  }

  return (
    <Page>
      <PageHeader
        title="Importar datos"
        subtitle="El zip del cliente se lee en el navegador; nada sale de este equipo."
        actions={
          dataset.meta.source === 'zip' ? (
            <Button variant="ghost" leadingIcon={<RotateCcw />} onClick={loadSample}>
              Volver a los datos de muestra
            </Button>
          ) : undefined
        }
      />
      <div className={styles.stack}>
        <div
          className={styles.drop}
          data-over={over || undefined}
          onDragOver={(e) => {
            e.preventDefault()
            setOver(true)
          }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
        >
          <FileArchive aria-hidden className={styles.dropIcon} />
          <p className={styles.dropTitle}>{status === 'loading' ? 'Leyendo el paquete…' : 'Arrastra aquí el zip del cliente'}</p>
          <p className={styles.dropHint}>CSV, JSON y JSONL se leen con el registro de tipos; el resto se guarda tal cual.</p>
          <Button variant="primary" leadingIcon={<Upload />} loading={status === 'loading'} onClick={() => input.current?.click()}>
            Elegir zip
          </Button>
          <input ref={input} type="file" accept=".zip" hidden onChange={(e) => take(e.target.files)} />
          {error && <p className={styles.error}>No se pudo leer el zip: {error}</p>}
        </div>

        <Card title="Datos cargados" description={`${dataset.meta.name} · ${formatDateTime(dataset.meta.loadedAt)}`}>
          <ul className={styles.counts}>
            {VIEWS.map((v) => (
              <li key={v.kind}>
                <v.icon aria-hidden />
                <span>{v.label}</span>
                <strong>{formatNumber(counts[v.kind])}</strong>
              </li>
            ))}
          </ul>
        </Card>

        <Section title="Ficheros sin reconocer" count={dataset.unmapped.length} description="Ningún tipo del registro los lee. Para que tengan pestaña, se añade su nombre en data/registry/mappings.ts.">
          {dataset.unmapped.length === 0 ? (
            <EmptyState size="sm" title="Todos los ficheros tienen tipo" />
          ) : (
            <ul className={styles.files}>
              {dataset.unmapped.map((f) => (
                <li key={f.path} className={styles.file}>
                  <div className={styles.fileHead}>
                    <Mono>{f.path}</Mono>
                    <span className={styles.fileMeta}>{kb(f.size)}</span>
                    {f.preview ? <Badge tone="info">{`${formatNumber(f.preview.length)} ${f.preview.length === 1 ? 'fila' : 'filas'} de muestra`}</Badge> : <Badge>No tabular</Badge>}
                  </div>
                  {f.preview && f.preview.length > 0 && (
                    <div className={styles.preview}>
                      <table>
                        <thead>
                          <tr>
                            {Object.keys(f.preview[0]).map((k) => (
                              <th key={k}>{k}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {f.preview.slice(0, 5).map((row, i) => (
                            <tr key={i}>
                              {Object.keys(f.preview![0]).map((k) => (
                                <td key={k}>{String(row[k] ?? '')}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Filas con problemas" count={dataset.issues.length} description="Filas que su tipo no pudo leer. El resto del fichero se cargó.">
          {dataset.issues.length === 0 ? (
            <EmptyState size="sm" title="Ninguna fila con problemas" />
          ) : (
            <ul className={styles.issues}>
              {dataset.issues.slice(0, 200).map((i, n) => (
                <li key={n}>
                  <Mono muted>
                    {i.path}:{i.row}
                  </Mono>
                  <span>{i.message}</span>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>
    </Page>
  )
}
