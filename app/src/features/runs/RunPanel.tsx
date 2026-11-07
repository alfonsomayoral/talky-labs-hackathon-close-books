import { ButtonLink, EmptyState, KeyValue, Mono, ProgressBar, Section, SidePanel, Skeleton, Amount } from '@/components'
import { useRun } from '@/data'
import { CASE_STATUS_LABEL, exceptionLabel, type CaseStatus, type Run } from '@/domain'
import { formatDateTime, formatDuration, formatNumber, formatPercent } from '@/lib/format'
import { BarList } from './BarList'
import { METRIC_LABEL, STAGE_LABEL, SUBMISSION_LIMIT_BYTES, formatBytes, stageList } from './model'
import styles from './RunPanel.module.css'

const byValue = (counts: Record<string, number>) =>
  Object.entries(counts)
    .map(([key, value]) => ({ key, value }))
    .sort((a, b) => b.value - a.value)

function CsvSize({ bytes }: { bytes: number | undefined }) {
  if (bytes == null) return <span className={styles.muted}>No registrado</span>
  const ratio = bytes / SUBMISSION_LIMIT_BYTES
  return (
    <div className={styles.size}>
      <ProgressBar size="sm" value={bytes} max={SUBMISSION_LIMIT_BYTES} tone={ratio >= 1 ? 'danger' : ratio >= 0.8 ? 'warn' : 'brand'} label="Tamaño del CSV frente al límite" />
      <span className="tabular">
        {formatBytes(bytes)} de {formatBytes(SUBMISSION_LIMIT_BYTES)} ({formatPercent(ratio)})
      </span>
    </div>
  )
}

function Detail({ run }: { run: Run }) {
  const stages = stageList(run.stages, null).filter((s) => s.ms != null)
  const models = Object.entries(run.models)
  return (
    <div className={styles.body}>
      <KeyValue
        labelWidth={150}
        items={[
          { label: 'Fase', value: run.phase, mono: true },
          { label: 'Fecha', value: formatDateTime(run.createdAt) },
          { label: 'Commit', value: run.gitCommit, mono: true },
          { label: 'Duración', value: formatDuration(run.durationMs) },
          { label: 'Movimientos', value: formatNumber(run.txns) },
          { label: 'Filas', value: formatNumber(run.rows) },
          { label: 'Reglas de memoria', value: formatNumber(run.memoryRulesApplied) },
          { label: 'Tamaño del CSV', value: <CsvSize bytes={run.csvBytes} /> },
        ]}
      />
      <Section title="Etapas">
        <BarList label="Duración por etapa" items={stages.map((s) => ({ key: s.stage, label: STAGE_LABEL[s.stage] ?? s.stage, value: s.ms!, display: formatDuration(s.ms) }))} />
      </Section>
      {run.score && (
        <Section title="Puntuación" description="Con el evaluador oficial, contra las respuestas de la fase.">
          <KeyValue
            labelWidth={190}
            items={[
              { label: 'Total', value: formatNumber(run.score.score, { decimals: 2 }) },
              ...Object.keys(METRIC_LABEL)
                .filter((k) => k in run.score!.metrics)
                .map((k) => ({ label: METRIC_LABEL[k], value: formatPercent(run.score!.metrics[k], { decimals: 1 }) })),
            ]}
          />
        </Section>
      )}
      <Section title="Casos">
        <BarList label="Casos por estado" items={byValue(run.cases).map((c) => ({ key: c.key, label: CASE_STATUS_LABEL[c.key as CaseStatus] ?? c.key, value: c.value }))} />
      </Section>
      <Section title="Filas por regla" count={Object.keys(run.byRule).length}>
        <BarList label="Filas por regla" items={byValue(run.byRule).map((r) => ({ key: r.key, label: <Mono>{r.key}</Mono>, value: r.value }))} />
      </Section>
      <Section title="Excepciones" count={Object.keys(run.byException).length}>
        <BarList label="Filas por excepción" items={byValue(run.byException).map((r) => ({ key: r.key, label: exceptionLabel(r.key), value: r.value }))} />
      </Section>
      <Section title="Categorías" count={Object.keys(run.byCategory).length}>
        <BarList label="Movimientos por categoría" items={byValue(run.byCategory).map((r) => ({ key: r.key, label: <Mono>{r.key}</Mono>, value: r.value }))} />
      </Section>
      <Section title="Modelos">
        {models.length === 0 ? (
          <p className={styles.muted}>Esta ejecución no ha llamado a ningún modelo.</p>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Modelo</th>
                <th scope="col">Llamadas</th>
                <th scope="col">Tokens de entrada</th>
                <th scope="col">Tokens de salida</th>
                <th scope="col">Coste</th>
              </tr>
            </thead>
            <tbody>
              {models.map(([name, m]) => (
                <tr key={name}>
                  <th scope="row">
                    <Mono>{name}</Mono>
                  </th>
                  <td className="tabular">{formatNumber(m.calls)}</td>
                  <td className="tabular">{formatNumber(m.inputTokens)}</td>
                  <td className="tabular">{formatNumber(m.outputTokens)}</td>
                  <td>
                    <Amount cents={Math.round(m.costUsd * 100)} currency="USD" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </div>
  )
}

/** Everything one run did (`?ver=<runId>`), with the way to look at it in the rest of the app. */
export function RunPanel({ runId, onClose }: { runId: string | null; onClose: () => void }) {
  const run = useRun(runId)
  return (
    <SidePanel
      open={runId != null}
      onClose={onClose}
      title={<Mono>{runId}</Mono>}
      aria-label="Detalle de la ejecución"
      defaultWidth={600}
      storageKey="runs-panel"
      footer={
        runId && (
          <ButtonLink variant="primary" to={{ pathname: '/', search: `?run=${encodeURIComponent(runId)}` }}>
            Ver esta ejecución
          </ButtonLink>
        )
      }
    >
      {run.data ? (
        <Detail run={run.data} />
      ) : run.error ? (
        <EmptyState title="No se ha podido cargar la ejecución" description={run.error.message} size="sm" />
      ) : (
        <div className={styles.body}>
          <Skeleton height={160} />
          <Skeleton height={120} />
        </div>
      )}
    </SidePanel>
  )
}
