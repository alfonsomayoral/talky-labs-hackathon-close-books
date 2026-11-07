import { useId, useState, type DragEvent, type ReactNode } from 'react'
import clsx from 'clsx'
import { Check, FileArchive, Play, RotateCcw, ShieldCheck, Terminal } from 'lucide-react'
import { Badge, Button, Card, KeyValue, Mono, ProgressBar, SegmentedControl, StatusDot } from '@/components'
import { useCurrentRun, useRun, useRunStatus, useRuns, useStartRun, useUpload, useValidateRun } from '@/data'
import { formatDuration, formatNumber } from '@/lib/format'
import { useTextParam } from '@/lib/urlState'
import { STAGE_LABEL, SUBMISSION_LIMIT_BYTES, consoleStep, formatBytes, stageList } from './model'
import styles from './FinalConsole.module.css'

const PHASES = ['live', 'holdout', 'final']
const MAX_ERRORS_SHOWN = 8

function Step({ n, current, title, summary, children }: { n: number; current: number; title: string; summary?: ReactNode; children?: ReactNode }) {
  const state = n < current ? 'done' : n === current ? 'current' : 'pending'
  return (
    <li className={clsx(styles.step, styles[state])} aria-current={state === 'current' ? 'step' : undefined}>
      <span className={styles.number} aria-hidden>
        {state === 'done' ? <Check /> : n}
      </span>
      <div className={styles.content}>
        <h4 className={styles.title}>{title}</h4>
        {summary != null && <div className={styles.summary}>{summary}</div>}
        {children}
      </div>
    </li>
  )
}

function Dropzone({ file, onFile }: { file: File | null; onFile: (f: File | null) => void }) {
  const id = useId()
  const [over, setOver] = useState(false)
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setOver(false)
    onFile(e.dataTransfer.files[0] ?? null)
  }
  return (
    <label
      htmlFor={id}
      className={clsx(styles.drop, over && styles.over)}
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
    >
      <FileArchive aria-hidden />
      <span>{file ? <Mono>{file.name}</Mono> : 'Arrastra aquí el zip de la fase o pulsa para elegirlo'}</span>
      {file && <span className={styles.muted}>{formatBytes(file.size)}</span>}
      <input id={id} className={styles.file} type="file" accept=".zip,application/zip" onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
    </label>
  )
}

export function FinalConsole() {
  const [consola, setConsola] = useTextParam('consola')
  const { runId: currentRunId } = useCurrentRun()
  const runs = useRuns()
  const status = useRunStatus(consola)
  const finished = status.data?.status === 'done'
  const run = useRun(finished ? consola : null)
  const upload = useUpload()
  const start = useStartRun()
  const validate = useValidateRun()
  const [phase, setPhase] = useState<string | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [withMemory, setWithMemory] = useState(false)

  const chosenPhase = consola ? (runs.data?.find((r) => r.runId === consola)?.phase ?? consola) : phase
  const validation = consola && validate.variables === consola ? (validate.data ?? null) : null
  const runStatus = consola ? (status.data?.status ?? 'running') : null
  const step = consoleStep({ phase: chosenPhase, status: runStatus, validation })
  const uploadedPhase = upload.data?.phase
  const phaseOptions = [...PHASES, ...(uploadedPhase && !PHASES.includes(uploadedPhase) ? [uploadedPhase] : [])].map((value) => ({ value, label: value }))
  const submissionPath = consola ? `runs/${consola}/submission.csv.gz` : ''

  const reset = () => {
    setConsola(null)
    setPhase(null)
    setFile(null)
    setWithMemory(false)
    upload.reset()
    start.reset()
    validate.reset()
  }
  const doUpload = () =>
    file &&
    upload.mutate(file, {
      onSuccess: (r) => {
        setPhase(r.phase)
        setFile(null)
      },
    })
  const doStart = () =>
    phase &&
    start.mutate({ phase, memoryFrom: withMemory && currentRunId ? currentRunId : undefined }, { onSuccess: (r) => setConsola(r.runId) })

  const stages = stageList(status.data?.stages ?? {}, status.data?.stage ?? null)
  const errors = validation?.errors ?? []

  return (
    <Card
      title="Consola FINAL"
      description="Del zip de la fase al fichero listo para que una persona lo envíe."
      actions={consola && <Button variant="ghost" size="sm" leadingIcon={<RotateCcw />} onClick={reset}>Nueva ejecución</Button>}
    >
      <ol className={styles.steps}>
        <Step n={1} current={step} title="Fase" summary={consola ? <>Fase <Mono>{chosenPhase}</Mono></> : phase ? <>Fase <Mono>{phase}</Mono> elegida</> : undefined}>
          {!consola && (
            <div className={styles.fields}>
              <SegmentedControl aria-label="Fase" options={phaseOptions} value={phase ?? ''} onChange={setPhase} />
              <span className={styles.muted}>o sube la fase nueva</span>
              <Dropzone file={file} onFile={setFile} />
              {file && (
                <div className={styles.row}>
                  <Button variant={step === 1 ? 'primary' : 'secondary'} loading={upload.isPending} onClick={doUpload}>
                    Subir zip
                  </Button>
                  {upload.error && <span className={styles.error}>{upload.error.message}</span>}
                </div>
              )}
            </div>
          )}
        </Step>

        <Step
          n={2}
          current={step}
          title="Ejecutar"
          summary={consola && status.data?.status === 'done' ? <>Terminada en {formatDuration(run.data?.durationMs ?? Object.values(status.data.stages).reduce((a, b) => a + b, 0))}</> : undefined}
        >
          {!consola ? (
            <div className={styles.fields}>
              <label className={styles.check}>
                <input type="checkbox" checked={withMemory} disabled={!currentRunId} onChange={(e) => setWithMemory(e.target.checked)} />
                <span>
                  Aplicar las reglas de memoria de la ejecución actual {currentRunId && <Mono>{currentRunId}</Mono>}
                </span>
              </label>
              <div className={styles.row}>
                <Button variant={step === 2 ? 'primary' : 'secondary'} leadingIcon={<Play />} disabled={!phase} loading={start.isPending} onClick={doStart}>
                  Ejecutar
                </Button>
                {start.error && <span className={styles.error}>{start.error.message}</span>}
              </div>
            </div>
          ) : status.error ? (
            <p className={styles.error}>{status.error.message}</p>
          ) : (
            <>
              <ul className={styles.stages} aria-label="Etapas de la ejecución">
                {stages.map((s) => (
                  <li key={s.stage} className={styles.stage}>
                    <StatusDot tone={s.state === 'done' ? 'ok' : s.state === 'running' ? 'info' : 'neutral'} pulse={s.state === 'running'} />
                    <span className={clsx(s.state === 'pending' && styles.muted)}>{STAGE_LABEL[s.stage] ?? s.stage}</span>
                    <span className={clsx(styles.muted, 'tabular')}>{s.ms != null ? formatDuration(s.ms) : s.state === 'running' ? 'en curso' : ''}</span>
                  </li>
                ))}
              </ul>
              {status.data?.status === 'failed' && <p className={styles.error}>La ejecución ha fallado{status.data.error ? `: ${status.data.error}` : '.'}</p>}
            </>
          )}
        </Step>

        <Step n={3} current={step} title="Validar">
          {finished && (
            <div className={styles.fields}>
              <div className={styles.row}>
                <Button variant={step === 3 ? 'primary' : 'secondary'} leadingIcon={<ShieldCheck />} loading={validate.isPending} onClick={() => consola && validate.mutate(consola)}>
                  {validation ? 'Validar de nuevo' : 'Validar'}
                </Button>
                {validate.error && <span className={styles.error}>{validate.error.message}</span>}
                {validation && <Badge tone={validation.ok ? 'ok' : 'danger'}>{validation.ok ? 'Válido' : 'No válido'}</Badge>}
              </div>
              {validation && (
                <>
                  <KeyValue
                    labelWidth={190}
                    items={[
                      { label: 'Filas', value: formatNumber(validation.rows) },
                      {
                        label: 'Movimientos cubiertos',
                        value: run.data ? (
                          <span className={validation.txns < run.data.txns ? styles.error : undefined}>
                            {formatNumber(validation.txns)} de {formatNumber(run.data.txns)}
                          </span>
                        ) : (
                          formatNumber(validation.txns)
                        ),
                      },
                      { label: 'Comprimido', value: formatBytes(validation.sizeBytes) },
                      {
                        label: 'Sin comprimir',
                        value: (
                          <div className={styles.size}>
                            <ProgressBar
                              size="sm"
                              value={validation.uncompressedBytes}
                              max={SUBMISSION_LIMIT_BYTES}
                              tone={validation.uncompressedBytes >= SUBMISSION_LIMIT_BYTES ? 'danger' : validation.uncompressedBytes >= 0.8 * SUBMISSION_LIMIT_BYTES ? 'warn' : 'brand'}
                              label="Tamaño sin comprimir frente al límite"
                            />
                            <span className="tabular">
                              {formatBytes(validation.uncompressedBytes)} de {formatBytes(SUBMISSION_LIMIT_BYTES)}
                            </span>
                          </div>
                        ),
                      },
                    ]}
                  />
                  {errors.length > 0 && (
                    <ul className={styles.errors} aria-label="Errores de validación">
                      {errors.slice(0, MAX_ERRORS_SHOWN).map((e, i) => (
                        <li key={i}>
                          {e.row != null && <Mono>fila {formatNumber(e.row)}</Mono>} {e.message}
                        </li>
                      ))}
                      {errors.length > MAX_ERRORS_SHOWN && <li className={styles.muted}>y {formatNumber(errors.length - MAX_ERRORS_SHOWN)} más</li>}
                    </ul>
                  )}
                </>
              )}
            </div>
          )}
        </Step>

        <Step n={4} current={step} title="Envío">
          <div className={clsx(styles.handoff, step === 4 && styles.ready)}>
            <Terminal aria-hidden />
            <div className={styles.handoffText}>
              <p>
                <strong>El envío lo hace una persona del equipo desde la terminal.</strong> Esta pantalla no envía nada.
              </p>
              <dl className={styles.commands}>
                <dt>Fichero</dt>
                <dd>
                  <Mono>{submissionPath || 'runs/<runId>/submission.csv.gz'}</Mono>
                </dd>
                <dt>Validación local</dt>
                <dd>
                  <Mono>closebooks validate {submissionPath || 'runs/<runId>/submission.csv.gz'}</Mono>
                </dd>
              </dl>
            </div>
          </div>
        </Step>
      </ol>
    </Card>
  )
}
