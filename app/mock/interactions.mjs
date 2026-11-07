// Walks the three interactions of the done criterion in a real browser and checks what they leave in human/.
// It writes for real: against `closebooks serve` it adds lines to runs/<id>/human/. Run it on a copy of the folder, never on the run to submit or to show.
//
//   npm i playwright@1.49.1 (outside the repo), start the API and the app, then:
//   PLAYWRIGHT=<dir>/node_modules/playwright/index.mjs node mock/interactions.mjs http://localhost:5173 [--run <id>] [--human <dir>] [--out <dir>] [--video]
//
// --out keeps a screenshot per step; --video also records it (needs `npx playwright install ffmpeg`).
// --human is the run's human/ folder, to read when the API is `closebooks serve`. Without it, the mock's GET …/human.
import { existsSync, mkdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const { chromium } = await import(process.env.PLAYWRIGHT ?? 'playwright')
const base = process.argv[2]
const option = (name) => (process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : null)
const humanDir = option('--human')
const out = option('--out')
if (out) mkdirSync(out, { recursive: true })

const browser = await chromium.launch({ channel: 'chrome' })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark', ...(out && process.argv.includes('--video') ? { recordVideo: { dir: out, size: { width: 1440, height: 900 } } } : {}) })
const page = await context.newPage()
const errors = []
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
page.on('pageerror', (e) => errors.push(e.message))

const runs = await (await page.request.get(`${base}/api/runs`)).json()
const runId = option('--run') ?? runs.find((r) => r.served)?.runId ?? runs[0].runId
const api = async (path) => (await page.request.get(`${base}/api/runs/${runId}${path}`)).json()
const jsonl = (file) => (existsSync(join(humanDir, file)) ? readFileSync(join(humanDir, file), 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l)) : [])
const human = async () => (humanDir ? { decisions: jsonl('decisions.jsonl'), memoryRules: jsonl('memory_rules.jsonl'), outbox: jsonl('outbox.jsonl') } : api('/human'))

let failed = 0
const check = (what, ok, detail = '') => {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}${detail ? ` · ${detail}` : ''}`)
  if (!ok) failed++
}
const open = async (caseId) => {
  await page.goto(`${base}/bandeja?run=${runId}&ver=${encodeURIComponent(caseId)}`)
  await page.waitForLoadState('networkidle')
  await page.locator('aside[role=complementary]').waitFor()
  return page.locator('aside[role=complementary]')
}
const shot = async (name) => out && page.screenshot({ path: join(out, `${name}.png`) })

// 1. Answer a question and save the answer as a rule.
const before = await human()
let now = before
const questions = (await api('/questions?status=open&size=200')).items
const question = questions.find((q) => q.rulePreview && q.options.some((o) => o.id !== 'none'))
check('hay una pregunta abierta con regla propuesta', Boolean(question), question?.questionId)
let panel
if (question) {
panel = await open(question.caseId)
await panel.getByRole('radio', { name: question.options.find((o) => o.id !== 'none').label }).check()
await panel.getByRole('checkbox', { name: /regla/i }).check()
await shot('1-pregunta')
await panel.getByRole('button', { name: /Responder/ }).click()
await page.waitForTimeout(800)
await shot('1-respondida')
now = await human()
const decision = now.decisions.at(-1)
const rule = now.memoryRules.at(-1)
check('la respuesta queda en decisions.jsonl', now.decisions.length === before.decisions.length + 1 && decision.questionId === question.questionId && decision.saveAsRule === true, decision?.optionId)
check('la regla queda en memory_rules.jsonl', now.memoryRules.length === before.memoryRules.length + 1 && rule.kind === question.rulePreview.kind, `${rule?.ruleId} ${rule?.kind}`)
check('la regla no conserva el texto provisional', !JSON.stringify(rule?.params ?? {}).includes('<la opción elegida>'), JSON.stringify(rule?.params))
check('el caso se cierra', (await api(`/cases/${encodeURIComponent(question.caseId)}`)).status === 'done')
await page.goto(`${base}/memoria?run=${runId}`)
await page.waitForLoadState('networkidle')
check('la regla se ve en Memoria', await page.getByText(rule.description).first().isVisible())
await shot('1-memoria')

}

// 2. Edit a draft and «send» it: nothing leaves, it is registered.
const draft = (await api('/drafts?status=draft&size=200')).items[0]
check('hay un borrador', Boolean(draft), draft?.draftId)
if (draft) {
panel = await open(draft.caseId)
const subject = `${draft.subject} (revisado)`
await panel.getByLabel('Asunto').fill(subject)
await shot('2-correo')
await panel.getByRole('button', { name: /^Enviar/ }).click()
await page.waitForTimeout(800)
await shot('2-enviado')
now = await human()
const sent = now.outbox.at(-1)
check('el envío queda en outbox.jsonl con el asunto editado', sent?.draftId === draft.draftId && sent?.status === 'sent' && sent?.subject === subject, sent?.subject)
check('el panel lo enseña como enviado', await panel.getByText('Enviado').first().isVisible())
}

// 3. Mark a case handled: it leaves the queue.
const stats = await api('/stats')
const handled = (await api('/cases?status=needs_review,fallback&size=200')).items.find((c) => !c.draftId && !c.questionId)
check('hay un caso que marcar', Boolean(handled), handled?.caseId)
if (handled) {
panel = await open(handled.caseId)
await panel.getByRole('button', { name: /gestionado/i }).click()
await page.waitForTimeout(800)
now = await human()
check('la decisión queda en decisions.jsonl', now.decisions.at(-1)?.caseId === handled.caseId && now.decisions.at(-1)?.action === 'done')
check('el caso pasa a gestionado', (await api(`/cases/${encodeURIComponent(handled.caseId)}`)).status === 'done')
const queue = (await api('/stats')).reviewQueue
check('la cola baja', queue < stats.reviewQueue, `${stats.reviewQueue} → ${queue}`)
await shot('3-gestionado')
}

check('cero errores en consola', errors.length === 0, errors.join(' | ').slice(0, 300))
await context.close()
await browser.close()
console.log(failed ? `${failed} comprobaciones fallidas` : 'Todo correcto')
process.exit(failed ? 1 : 0)
