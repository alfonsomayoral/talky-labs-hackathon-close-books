// The figures of docs/DEMO.md and docs/SUBMISSION.md, from the run the API serves, to paste over their <…>.
//   node mock/figures.mjs http://localhost:8000
const base = process.argv[2] ?? 'http://localhost:8000'
const get = async (path) => (await fetch(`${base}/api${path}`)).json()
const runs = await get('/runs')
const run = runs.find((r) => r.served) ?? runs[0]
const stats = await get(`/runs/${run.runId}/stats`)
const es = (n, digits = 0) => n.toLocaleString('es-ES', { minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping: 'always' })
const rows = [
  ['Ejecución', run.runId],
  ['<X> % cerrado sin intervención', `${es((stats.txnsAuto / stats.txns) * 100, 1)} %`],
  ['<N> movimientos (SUBMISSION)', es(stats.txns)],
  ['<N> casos en cola (DEMO, paso 1)', es(stats.reviewQueue)],
  ['Identificado', `${es(stats.identifiedEur / 1e8, 1)} M€ de ${es(stats.totalEur / 1e8, 1)} M€`],
  ['<Y>/<C> dólares de modelo', es(run.modelCostUsd, 2)],
  ['<M> llamadas a modelo', es(run.modelCalls)],
  ['<T>/<Z> minutos de la ejecución', es(run.durationMs / 60000, 1)],
  ['Filas de la entrega', es(run.rows)],
  ['Puntuación local (solo si la fase tiene golden)', run.score == null ? 'sin golden' : es(run.score, 2)],
]
for (const [label, value] of rows) console.log(`${label.padEnd(48)} ${value}`)
console.log('\n<S> y <F> (LIVE y FINAL) son de la clasificación: no salen de aquí.')
