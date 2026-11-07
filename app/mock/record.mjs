// Records the eight steps of docs/DEMO.md as a video, with their pauses. Screen only: the voice goes on top.
//
//   npm i playwright@1.49.1 (outside the repo), then `npx playwright install ffmpeg`, start the API and the app:
//   PLAYWRIGHT=<dir>/node_modules/playwright/index.mjs node mock/record.mjs http://localhost:5173 --out <dir> [--ids ids.json] [--write]
//
// Without --write it only shows the steps and clicks nothing that saves. With --write it answers, sends and
// saves a rule for real in runs/<id>/human/: use a COPY of the run, never the one to submit.
// The ids are those of docs/DEMO.md; --ids replaces any of them with another run's.
import { mkdirSync, readFileSync, renameSync } from 'node:fs'
import { join } from 'node:path'

const { chromium } = await import(process.env.PLAYWRIGHT ?? 'playwright')
const base = process.argv[2]
const option = (name) => (process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : null)
const out = option('--out') ?? 'recording'
const write = process.argv.includes('--write')
const ids = {
  advice: 'BT-2025-0200180',
  questionCase: 'CASE-BT-2025-0378685',
  customer: 'CES01000094',
  incident: 'CASE-BT-2025-0293358-API-2025-7506669',
  account: null,
  ...(option('--ids') ? JSON.parse(readFileSync(option('--ids'), 'utf8')) : {}),
}
mkdirSync(out, { recursive: true })

const browser = await chromium.launch({ channel: 'chrome' })
const size = { width: 1440, height: 900 }
const context = await browser.newContext({ viewport: size, colorScheme: 'dark', recordVideo: { dir: out, size } })
const page = await context.newPage()
const errors = []
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
page.on('pageerror', (e) => errors.push(e.message))

const hold = (seconds) => page.waitForTimeout(seconds * 1000)
const panel = () => page.locator('aside[role=complementary]')
const go = async (path) => {
  await page.goto(base + path)
  await page.waitForSelector('h1')
  await page.waitForLoadState('networkidle')
}
const scrollPanel = async (pixels) => {
  await panel().hover()
  await page.mouse.wheel(0, pixels)
}
const step = async (n, seconds, run) => {
  const start = Date.now()
  console.log(`Paso ${n}`)
  await run()
  // Each step lasts what the script gives it, whatever the clicks took.
  await page.waitForTimeout(Math.max(0, seconds * 1000 - (Date.now() - start)))
}

try {
  // Seconds per step are those of docs/DEMO.md, and add up to 5 minutes.
  await step(1, 40, async () => {
    await go('/')
    await hold(12)
    await page.mouse.wheel(0, 500)
    await hold(10)
    await page.mouse.wheel(0, -500)
  })
  await step(2, 60, async () => {
    await go(`/conciliacion?ver=${encodeURIComponent(ids.advice)}`)
    await hold(18)
    await scrollPanel(450)
    await hold(18)
    await scrollPanel(600)
  })
  await step(3, 60, async () => {
    await go(`/bandeja?ver=${encodeURIComponent(ids.questionCase)}`)
    await hold(14)
    await panel().getByRole('radio').first().check()
    await hold(5)
    await panel().getByRole('checkbox', { name: /regla/i }).check()
    await hold(10)
    if (write) {
      await panel().getByRole('button', { name: /Responder/ }).click()
      await hold(4)
      await go('/memoria')
    }
  })
  await step(4, 40, async () => {
    await go(`/cobros?ver=${encodeURIComponent(ids.customer)}`)
    await hold(10)
    await panel().getByLabel('Asunto').fill('Facturas vencidas: les rogamos que nos confirmen la fecha de pago')
    await hold(10)
    if (write) await panel().getByRole('button', { name: /^Enviar/ }).click()
  })
  await step(5, 20, async () => {
    await go(`/proveedores?ver=${encodeURIComponent(ids.incident)}`)
  })
  await step(6, 20, async () => {
    await go('/memoria')
  })
  await step(7, 25, async () => {
    await go('/cuentas')
    await hold(11)
    await go('/explorador?tipo=documents')
  })
  await step(8, 35, async () => {
    await go('/ejecuciones')
    await hold(10)
    await go('/ejecuciones?vista=comparar')
    await hold(10)
    await go('/ejecuciones?vista=final')
  })
} finally {
  const video = page.video()
  await context.close()
  await browser.close()
  if (video) renameSync(await video.path(), join(out, 'demo.webm'))
}
console.log(`Vídeo en ${join(out, 'demo.webm')}`)
if (errors.length) {
  console.log(`Errores de consola: ${errors.join(' | ').slice(0, 500)}`)
  process.exit(1)
}
