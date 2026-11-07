// Final screenshots: the nine screens and their panels, in both themes, from whatever run the API serves.
//   PLAYWRIGHT=<dir>/node_modules/playwright/index.mjs node mock/capture.mjs http://localhost:5173 docs/screenshots/final
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'

const { chromium } = await import(process.env.PLAYWRIGHT ?? 'playwright')
const [base, out] = process.argv.slice(2)
mkdirSync(out, { recursive: true })

const get = async (path) => (await fetch(`${base}/api${path}`)).json()
const runs = await get('/runs')
const run = runs.find((r) => r.served) ?? runs[0]
const list = async (path) => (await get(`/runs/${run.runId}${path}`)).items ?? []
console.log('Ejecución:', run.runId)

const advice = (await list('/transactions?rule=ADVICE-CSV,ADVICE-TXT,ADVICE-XLSX,ADVICE-PDF&size=1'))[0]
const fileRun = (await list('/transactions?rule=FILE-PAYMENT-RUN&size=1'))[0]
const question = (await list('/questions?status=open&size=1'))[0]
const draft = (await list('/drafts?status=draft&size=1'))[0]
const incident = (await list('/cases?kind=supplier_invoice_mismatch&sort=priority,-amountEur&size=1'))[0]
const customer = (await get(`/runs/${run.runId}/aging?partyKind=customer`)).parties?.[0]

const shots = [
  ['resumen', '/'],
  ['bandeja', '/bandeja'],
  ['conciliacion', '/conciliacion'],
  ['cobros', '/cobros'],
  ['proveedores', '/proveedores'],
  ['cuentas', '/cuentas'],
  ['explorador', '/explorador'],
  ['memoria', '/memoria'],
  ['ejecuciones', '/ejecuciones'],
  ['consola-final', '/ejecuciones?vista=final'],
  ...(advice ? [['conciliacion-aviso', `/conciliacion?ver=${advice.bankTxnId}`]] : []),
  ...(fileRun ? [['conciliacion-remesa', `/conciliacion?ver=${fileRun.bankTxnId}`]] : []),
  ...(question ? [['bandeja-pregunta', `/bandeja?ver=${question.caseId}`]] : []),
  ...(draft ? [['bandeja-correo', `/bandeja?ver=${draft.caseId}`]] : []),
  ...(customer ? [['cobros-cliente', `/cobros?ver=${customer.partyId}`]] : []),
  ...(incident ? [['proveedores-incidencia', `/proveedores?ver=${incident.caseId}`]] : []),
]

const browser = await chromium.launch({ channel: 'chrome' })
let errors = 0
try {
  for (const [scheme, theme] of [['dark', 'oscuro'], ['light', 'claro']]) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: scheme })
    for (const [name, path] of shots) {
      const page = await context.newPage()
      const seen = []
      page.on('console', (m) => m.type() === 'error' && seen.push(m.text().slice(0, 120)))
      page.on('pageerror', (e) => seen.push(e.message.slice(0, 120)))
      await page.goto(base + path)
      await page.waitForSelector('h1')
      await page.waitForLoadState('networkidle')
      await page.waitForTimeout(500)
      await page.screenshot({ path: join(out, `${name}-${theme}.png`) })
      if (seen.length) {
        errors += seen.length
        console.log('ERROR', name, theme, seen.join(' | '))
      }
      await page.close()
    }
    await context.close()
  }
} finally {
  await browser.close()
}
const missing = [!advice && 'aviso', !question && 'pregunta', !draft && 'borrador', !incident && 'incidencia'].filter(Boolean)
console.log(`${shots.length * 2} capturas en ${out}; ${errors} errores de consola${missing.length ? `; sin datos para: ${missing.join(', ')}` : ''}`)
process.exit(errors ? 1 : 0)
