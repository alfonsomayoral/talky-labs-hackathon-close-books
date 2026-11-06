// API of CONTRACT.md §5 on :8000 over fixtures/run-sample/. Same routes and shapes as `closebooks serve`,
// so the app does not know which one it talks to. What a person writes (human/) lives in memory.
// `node mock/server.mjs --run ../runs/live-<ts>` serves a real run folder instead of the fixtures.
import { createServer } from 'node:http'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { loadRealRun } from './realRun.mjs'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const PORT = Number(process.env.PORT ?? 8000)
const runArg = process.argv.indexOf('--run')

function loadFixtures() {
  const dir = join(ROOT, 'fixtures', 'run-sample')
  const jsonl = (name) => readFileSync(join(dir, name), 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l))
  return {
    run: JSON.parse(readFileSync(join(dir, 'run.json'), 'utf8')), masters: JSON.parse(readFileSync(join(dir, 'masters.json'), 'utf8')), asOf: '2025-12-31',
    txns: jsonl('transactions.jsonl'), explanations: jsonl('explanations.jsonl'), cases: jsonl('cases.jsonl'), questions: jsonl('questions.jsonl'), drafts: jsonl('drafts.jsonl'), openItems: jsonl('open_items.jsonl'),
    parties: jsonl('parties.jsonl'), partyFacts: jsonl('party_facts.jsonl'), items: jsonl('items.jsonl'), documents: jsonl('documents.jsonl'), documentFacts: jsonl('document_facts.jsonl'), detailFiles: jsonl('detail_files.jsonl'),
    documentText: (path, doc) => doc.text ?? null,
    detailRows: null,
  }
}

const data = runArg > 0 ? await loadRealRun(process.argv[runArg + 1], process.argv[process.argv.indexOf('--db') + 1] ?? join(ROOT, '..', 'db')) : loadFixtures()
const { run, masters, txns, explanations, cases, questions, drafts, openItems, parties, partyFacts, items, documents, documentFacts, detailFiles } = data

const human = { decisions: [], memoryRules: [], outbox: [] }
const runs = new Map([[run.runId, { run, status: { runId: run.runId, status: 'done', stage: null, stages: run.stages, startedAt: run.createdAt, finishedAt: run.createdAt, error: null } }]])

const groupBy = (list, key) => {
  const map = new Map()
  for (const x of list) {
    const k = key(x)
    const bucket = map.get(k)
    if (bucket) bucket.push(x)
    else map.set(k, [x])
  }
  return map
}
const rowsByTxn = groupBy(explanations, (e) => e.bankTxnId)
const itemById = new Map(items.map((i) => [i.itemId, i]))
const openById = new Map(openItems.map((i) => [i.itemId, i]))
const partyById = new Map(parties.map((p) => [p.partyId, p]))
const caseByTxn = new Map(cases.filter((c) => c.bankTxnId).map((c) => [c.bankTxnId, c]))
const caseById = new Map(cases.map((c) => [c.caseId, c]))
const factByTxn = new Map(partyFacts.map((f) => [f.bankTxnId, f]))
const txnById = new Map(txns.map((t) => [t.bankTxnId, t]))
const documentByPath = new Map(documents.map((d) => [d.path, d]))
const detailFileByPath = new Map(detailFiles.map((f) => [f.path, f]))
const QUEUE = new Set(['needs_review', 'question', 'fallback'])

const normalize = (s) => String(s ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()
const values = (v) => (v ? v.split(',') : null)

function txnRow(t) {
  const rows = rowsByTxn.get(t.bankTxnId) ?? []
  const c = caseByTxn.get(t.bankTxnId)
  const fact = factByTxn.get(t.bankTxnId)
  return {
    bankTxnId: t.bankTxnId, accountId: t.accountId, entity: t.entity, bank: t.bank, statementFormat: t.statementFormat, bookingDate: t.bookingDate, amountCents: t.amountCents, currency: t.currency, amountEur: t.amountEur,
    text: t.text, counterpartyName: t.counterpartyName, rule: rows[0]?.rule ?? 'FALLBACK-CATEGORY', confidence: rows[0]?.confidence ?? 0, partyId: fact?.partyId ?? null, partyName: fact ? partyById.get(fact.partyId)?.name ?? null : null,
    caseId: c?.caseId ?? null, caseStatus: c?.status ?? null, rowCount: rows.length,
    assignments: rows.slice(0, 5).map((r) => ({ itemId: r.itemId, documentNumber: r.documentNumber, amountCents: r.amountCents, currency: r.currency, category: r.category, exception: r.exception })),
  }
}
const caseRow = (c) => ({ ...c, partyName: c.partyId ? partyById.get(c.partyId)?.name ?? null : null })
const draftById = (id) => {
  const d = drafts.find((x) => x.draftId === id)
  return d ?? null
}
const caseDetail = (c) => ({ ...caseRow(c), question: c.questionId ? questions.find((q) => q.questionId === c.questionId) ?? null : null, draft: c.draftId ? draftById(c.draftId) : null })

const statsCache = new Map()
function stats(entity) {
  const key = entity ?? ''
  if (!statsCache.has(key)) statsCache.set(key, computeStats(entity))
  return statsCache.get(key)
}

function computeStats(entity) {
  const scoped = entity ? txns.filter((t) => t.entity === entity) : txns
  const scopedCases = entity ? cases.filter((c) => c.entity === entity) : cases
  const inQueue = (t) => QUEUE.has(caseByTxn.get(t.bankTxnId)?.status)
  const sum = (list, f) => list.reduce((a, x) => a + f(x), 0)
  const summary = (list) => ({ txns: list.length, txnsAuto: list.filter((t) => !inQueue(t)).length, reviewQueue: list.filter(inQueue).length, identifiedEur: sum(list.filter((t) => t.identified), (t) => Math.abs(t.amountEur)) })
  const scopedRows = entity ? scoped.flatMap((t) => rowsByTxn.get(t.bankTxnId) ?? []) : explanations
  const queue = scopedCases.filter((c) => QUEUE.has(c.status))
  const eurOf = (r) => Math.abs(txnById.get(r.bankTxnId)?.amountEur ?? 0)
  const tally = (key) => [...groupBy(scopedRows.filter((r) => r[key]), (r) => r[key])]
  return {
    runId: run.runId, phase: run.phase, entity: entity ?? null, periodFrom: txns.reduce((a, t) => (t.bookingDate < a ? t.bookingDate : a), txns[0].bookingDate), periodTo: data.asOf, ...summary(scoped), reviewQueue: queue.length, totalEur: sum(scoped, (t) => Math.abs(t.amountEur)), reviewQueueEur: sum(queue, (c) => c.amountEur),
    byStatus: Object.fromEntries([...groupBy(scopedCases, (c) => c.status)].map(([k, v]) => [k, v.length])),
    byKind: [...groupBy(scopedCases, (c) => c.kind)].map(([kind, v]) => ({ kind, cases: v.length, amountEur: sum(v, (c) => c.amountEur) })).sort((a, b) => b.cases - a.cases),
    byEntity: [...groupBy(txns, (t) => t.entity)].map(([e, v]) => ({ entity: e, name: masters.entities.find((x) => x.entity === e)?.name ?? e, ...summary(v) })).sort((a, b) => b.txns - a.txns),
    byRule: [...groupBy(scopedRows, (r) => r.rule)].map(([rule, v]) => ({ rule, rows: v.length, txns: new Set(v.map((r) => r.bankTxnId)).size })).sort((a, b) => b.rows - a.rows),
    byException: tally('exception').map(([exception, v]) => ({ exception, rows: v.length, amountEur: sum(v, (r) => r.amountCents ?? eurOf(r)) })).sort((a, b) => b.rows - a.rows),
    byCategory: tally('category').map(([category, v]) => ({ category, txns: v.length, amountEur: sum(v, eurOf) })).sort((a, b) => b.txns - a.txns),
    byDay: [...groupBy(scoped, (t) => t.bookingDate)].sort(([a], [b]) => a.localeCompare(b)).map(([date, v]) => ({ date, ...summary(v) })),
    score: run.score,
  }
}

// Scrolling asks for page after page with the same filters: keep the last filtered and sorted list.
const lastList = { key: null, source: null, rows: null }

function list(all, query, { search, filters = {}, map = (r) => r, sortValue = (r, key) => r[key] } = {}) {
  const params = new URLSearchParams(query)
  params.delete('page')
  params.delete('size')
  const key = params.toString()
  let rows
  if (lastList.source === all && lastList.key === key) rows = lastList.rows
  else {
    rows = all
    for (const [param, field] of Object.entries(filters)) {
      const allowed = values(query.get(param))
      if (allowed) rows = rows.filter((r) => allowed.includes(String(r[field])))
    }
    const q = normalize(query.get('q'))
    if (q && search) rows = rows.filter((r) => search(r).some((s) => normalize(s).includes(q)))
    const sort = query.get('sort')
    if (sort) {
      const desc = sort.startsWith('-')
      const field = desc ? sort.slice(1) : sort
      const decorated = rows.map((r) => [sortValue(r, field), r])
      decorated.sort(([x], [y]) => {
        if (x == null || y == null) return x == null ? (y == null ? 0 : 1) : -1
        const cmp = x < y ? -1 : x > y ? 1 : 0
        return desc ? -cmp : cmp
      })
      rows = decorated.map((d) => d[1])
    }
    Object.assign(lastList, { key, source: all, rows })
  }
  const page = Math.max(1, Number(query.get('page') ?? 1))
  const size = Math.min(200, Number(query.get('size') ?? 50))
  return { items: rows.slice((page - 1) * size, page * size).map(map), total: rows.length, page, size }
}

function txnDetail(t) {
  const rows = rowsByTxn.get(t.bankTxnId) ?? []
  const { amountEur, identified, ...txn } = t
  const fact = factByTxn.get(t.bankTxnId)
  const party = fact && partyById.get(fact.partyId)
  const sources = [...new Map(rows.flatMap((r) => r.sources).map((s) => [`${s.kind}:${s.ref}`, s])).values()]
  const evidence = sources.map((s) => {
    const doc = documentByPath.get(s.ref)
    if (doc) return { ...s, content: { type: 'document', path: doc.path, text: data.documentText(doc.path, doc), facts: documentFacts.filter((f) => f.docPath === doc.path) } }
    if (detailFileByPath.has(s.ref)) {
      const table = data.detailRows?.(s.ref, rows.map((r) => r.documentNumber)) ?? { columns: ['item', 'documento', 'importe', 'moneda'], rows: rows.map((r) => [r.itemId, r.documentNumber, ((r.amountCents ?? 0) / 100).toFixed(2), r.currency]) }
      return { ...s, content: { type: 'detailFile', path: s.ref, ...table } }
    }
    const master = partyById.get(s.ref)
    if (master) return { ...s, content: { type: 'record', fields: { Nombre: master.name, Sociedad: master.entity, IBAN: master.iban, Condiciones: master.paymentTerms, Grupo: master.groupId } } }
    return { ...s, content: { type: 'none' } }
  })
  const dup = rows[0]?.rule === 'HISTORY-DUPLICATE' ? rows[0].sources[0]?.ref : null
  const original = dup && txnById.get(dup)
  return {
    txn, party: fact ? { partyId: fact.partyId, partyName: party?.name ?? fact.partyId, partyKind: fact.partyKind, payerName: fact.payerName, how: fact.how, confidence: fact.confidence, alternatives: [] } : null,
    rows: rows.map(({ documentNumber, ...r }) => {
      const item = r.itemId ? itemById.get(r.itemId) : null
      const open = r.itemId ? openById.get(r.itemId) : null
      return { ...r, item: item ? { itemId: item.itemId, itemType: item.itemType, documentNumber: item.documentNumber, partyId: item.partyId, partyName: item.partyName, issueDate: item.issueDate, dueDate: item.dueDate, currency: item.currency, totalCents: item.totalCents, openAtStartCents: open?.openAtStartCents ?? null, openAtEndCents: open?.openAtEndCents ?? null } : null }
    }),
    candidates: rows[0]?.candidates ?? [], evidence, related: original ? [{ bankTxnId: original.bankTxnId, bookingDate: original.bookingDate, amountCents: original.amountCents, currency: original.currency, text: original.text, relation: 'duplicateOf' }] : [],
    case: caseByTxn.has(t.bankTxnId) ? caseByTxn.get(t.bankTxnId) : null,
  }
}

const BUCKETS = ['not_due', 'd1_30', 'd31_60', 'd61_90', 'd90_plus']
const bucketOf = (d) => (d <= 0 ? 'not_due' : d <= 30 ? 'd1_30' : d <= 60 ? 'd31_60' : d <= 90 ? 'd61_90' : 'd90_plus')
const emptyBuckets = () => Object.fromEntries(BUCKETS.map((b) => [b, 0]))
function aging(entity, kind) {
  const type = kind === 'supplier' ? 'API' : 'ARI'
  const open = openItems.filter((i) => i.itemType === type && i.openAtEndCents > 0 && (!entity || i.entity === entity))
  const totals = emptyBuckets()
  const byParty = new Map()
  for (const i of open) {
    const bucket = bucketOf(i.daysOverdue)
    totals[bucket] += i.openAtEndEur
    const p = byParty.get(i.partyId) ?? { partyId: i.partyId, partyName: i.partyName, entity: i.entity, openEur: 0, overdueEur: 0, buckets: emptyBuckets(), openItems: 0, oldestDaysOverdue: 0, disputes: 0, duplicates: 0, caseId: null }
    p.openEur += i.openAtEndEur
    if (i.daysOverdue > 0) p.overdueEur += i.openAtEndEur
    p.buckets[bucket] += i.openAtEndEur
    p.openItems++
    p.oldestDaysOverdue = Math.max(p.oldestDaysOverdue, i.daysOverdue)
    if (i.status === 'disputed') p.disputes++
    byParty.set(i.partyId, p)
  }
  for (const c of cases) {
    const p = c.partyId && byParty.get(c.partyId)
    if (!p) continue
    if (c.kind === 'overdue_customer') p.caseId = c.caseId
    if (c.kind === 'duplicate_payment') p.duplicates++
  }
  const parties2 = [...byParty.values()].sort((a, b) => b.overdueEur - a.overdueEur).slice(0, 200)
  return { asOf: data.asOf, totals, openEur: Object.values(totals).reduce((a, b) => a + b, 0), overdueEur: Object.values(totals).reduce((a, b) => a + b, 0) - totals.not_due, parties: parties2 }
}

const accountsCache = new Map()
const cached = (cache, key, compute) => {
  if (!cache.has(key)) cache.set(key, compute())
  return cache.get(key)
}

function accountsOf(runId) {
  return masters.accounts.map((a) => {
    const own = txns.filter((t) => t.accountId === a.accountId)
    const inflow = own.filter((t) => t.amountCents > 0).reduce((s, t) => s + t.amountCents, 0)
    const outflow = own.filter((t) => t.amountCents < 0).reduce((s, t) => s - t.amountCents, 0)
    const dates = own.map((t) => t.bookingDate).sort()
    return { ...a, txns: own.length, inflowCents: inflow, outflowCents: outflow, netCents: inflow - outflow, firstDate: dates[0] ?? null, lastDate: dates.at(-1) ?? null, reconciledRate: runId && own.length ? own.filter((t) => !QUEUE.has(caseByTxn.get(t.bankTxnId)?.status)).length / own.length : null }
  }).filter((a) => a.txns > 0 || a.inMaster)
}

const summaryOf = (r) => {
  const models = Object.values(r.models ?? {})
  const { stages, byRule, byException, byCategory, models: _m, dataDir, score, ...rest } = r
  return { ...rest, modelCalls: models.reduce((a, m) => a + m.calls, 0), modelCostUsd: models.reduce((a, m) => a + m.costUsd, 0), score: score?.score ?? null }
}

class Problem extends Error {
  constructor(status, detail) {
    super(detail)
    this.status = status
  }
}
const found = (x, what) => {
  if (x == null) throw new Problem(404, `No existe ${what}`)
  return x
}
const now = () => new Date().toISOString()
const decisionId = () => `DEC-${String(human.decisions.length + 1).padStart(6, '0')}`

function startRun(body) {
  const stamp = new Date().toISOString().replace(/\D/g, '').slice(0, 14)
  const runId = `${body.phase}-${stamp.slice(0, 8)}-${stamp.slice(8)}`
  const copy = { ...run, runId, phase: body.phase, createdAt: now(), memoryRulesApplied: human.memoryRules.filter((r) => r.active).length }
  const status = { runId, status: 'running', stage: 'load', stages: {}, startedAt: now(), finishedAt: null, error: null }
  runs.set(runId, { run: copy, status })
  const stages = Object.keys(run.stages)
  stages.forEach((stage, i) => setTimeout(() => {
    status.stages[stage] = run.stages[stage]
    status.stage = stages[i + 1] ?? null
    if (i === stages.length - 1) Object.assign(status, { status: 'done', finishedAt: now() })
  }, (i + 1) * 1500))
  return { runId, status: 'running' }
}

async function route(method, path, query, readBody) {
  const seg = path.split('/').filter(Boolean).map(decodeURIComponent)
  if (seg[0] !== 'api') throw new Problem(404, 'Ruta desconocida')

  if (seg[1] === 'uploads' && method === 'POST') {
    await readBody(true)
    return { uploadId: `upload-${Date.now()}`, phase: `upload-${Date.now()}` }
  }

  if (seg[1] === 'data') {
    const resource = seg[3]
    if (resource === 'accounts') return cached(accountsCache, query.get('runId') ?? '', () => accountsOf(query.get('runId')))
    if (resource === 'items') return list(items, query, { search: (r) => [r.itemId, r.documentNumber, r.partyName], filters: { type: 'itemType', entity: 'entity', partyId: 'partyId' } })
    if (resource === 'parties') return list(parties, query, { search: (r) => [r.partyId, r.name, r.taxId], filters: { kind: 'kind', entity: 'entity' } })
    if (resource === 'detail-files') return list(detailFiles, query, { filters: { kind: 'kind', entity: 'entity' } })
    if (resource === 'documents' && seg.length > 4) {
      const doc = found(documentByPath.get(seg.slice(4).join('/')), 'ese documento')
      const { text, ...row } = doc
      return { ...row, text: data.documentText(doc.path, doc), facts: documentFacts.filter((f) => f.docPath === doc.path) }
    }
    if (resource === 'documents') return list(documents, query, { map: ({ text, ...d }) => d, search: (r) => [r.path, r.partyName], filters: { kind: 'kind', entity: 'entity' } })
    throw new Problem(404, 'Ruta desconocida')
  }

  if (seg[1] !== 'runs') throw new Problem(404, 'Ruta desconocida')
  if (seg.length === 2 && method === 'GET') return [...runs.values()].map((r) => summaryOf(r.run)).sort((a, b) => b.createdAt.localeCompare(a.createdAt))
  if (seg.length === 2 && method === 'POST') return startRun(await readBody())
  const current = found(runs.get(seg[2]), 'esa ejecución')
  const resource = seg[3]
  if (!resource) return current.run
  if (resource === 'status') return current.status
  if (resource === 'stats') return stats(query.get('entity'))
  if (resource === 'validate') return { ok: true, errors: [], sizeBytes: 9200000, uncompressedBytes: 34500000, rows: run.rows, txns: run.txns }

  if (resource === 'transactions') {
    if (seg[4]) return txnDetail(found(txnById.get(seg[4]), 'ese movimiento'))
    let rows = txns
    const rule = values(query.get('rule'))
    const exception = values(query.get('exception'))
    const category = values(query.get('category'))
    const from = query.get('from')
    const to = query.get('to')
    if (rule || exception || category) {
      rows = rows.filter((t) => {
        const own = rowsByTxn.get(t.bankTxnId) ?? []
        return (!rule || own.some((r) => rule.includes(r.rule))) && (!exception || own.some((r) => exception.includes(r.exception))) && (!category || own.some((r) => category.includes(r.category)))
      })
    }
    if (from) rows = rows.filter((t) => t.bookingDate >= from)
    if (to) rows = rows.filter((t) => t.bookingDate <= to)
    const statuses = values(query.get('caseStatus'))
    if (statuses) rows = rows.filter((t) => statuses.includes(String(caseByTxn.get(t.bankTxnId)?.status)))
    const page = list(rows, query, {
      map: txnRow,
      search: (t) => [t.bankTxnId, t.text, t.counterpartyName, ...(rowsByTxn.get(t.bankTxnId) ?? []).map((x) => x.documentNumber)],
      filters: { entity: 'entity', accountId: 'accountId' },
      sortValue: (t, key) => (key === 'rowCount' ? rowsByTxn.get(t.bankTxnId)?.length : key === 'rule' ? rowsByTxn.get(t.bankTxnId)?.[0]?.rule : key === 'confidence' ? rowsByTxn.get(t.bankTxnId)?.[0]?.confidence : key === 'caseStatus' ? caseByTxn.get(t.bankTxnId)?.status : t[key]),
    })
    return page
  }

  if (resource === 'cases') {
    if (!seg[4]) return list(cases, query, { map: caseRow, sortValue: (c, key) => (key === 'partyName' ? partyById.get(c.partyId)?.name : c[key]), search: (c) => [c.caseId, c.summary, partyById.get(c.partyId)?.name], filters: { status: 'status', kind: 'kind', entity: 'entity', priority: 'priority' } })
    const c = found(caseById.get(seg[4]), 'ese caso')
    if (seg[5] === 'decision' && method === 'POST') {
      const body = await readBody()
      human.decisions.push({ decisionId: decisionId(), caseId: c.caseId, ...body, at: now() })
      if (body.action === 'done') c.status = 'done'
      statsCache.clear()
      accountsCache.clear()
      return caseDetail(c)
    }
    return caseDetail(c)
  }

  if (resource === 'questions') {
    if (seg[5] === 'answer' && method === 'POST') {
      const q = found(questions.find((x) => x.questionId === seg[4]), 'esa pregunta')
      const body = await readBody()
      human.decisions.push({ decisionId: decisionId(), questionId: q.questionId, caseId: q.caseId, ...body, at: now() })
      q.status = 'answered'
      const c = caseById.get(q.caseId)
      c.status = 'done'
      statsCache.clear()
      accountsCache.clear()
      if (body.saveAsRule && q.rulePreview) {
        const { kind, description, ...params } = q.rulePreview
        human.memoryRules.push({ ruleId: `MR-${String(human.memoryRules.length + 1).padStart(4, '0')}`, kind, params: { ...params, partyId: itemById.get(body.optionId)?.partyId ?? params.partyId }, description, scope: { entity: q.entity }, createdFrom: { questionId: q.questionId, caseId: q.caseId }, by: body.by, at: now(), active: true })
      }
      return caseDetail(c)
    }
    return list(questions, query, { filters: { status: 'status', entity: 'entity' } })
  }

  if (resource === 'drafts') {
    if (seg.length === 4 && method === 'POST') {
      const body = await readBody()
      const c = found(caseById.get(body.caseId), 'ese caso')
      if (c.draftId) return draftById(c.draftId)
      const party = c.partyId ? partyById.get(c.partyId) : null
      const draft = { draftId: `D-${String(drafts.length + 1).padStart(6, '0')}`, caseId: c.caseId, kind: body.kind, to: `administracion@${String(party?.partyId ?? 'tercero').toLowerCase()}.example`, toName: party?.name ?? 'Tercero', partyId: c.partyId, language: 'es', subject: `Sobre: ${c.summary.slice(0, 60)}`, body: `Estimados señores:\n\n${c.summary}\n\nQuedamos a la espera de su respuesta.\n\nUn saludo,\nTesorería`, attachments: [], generatedBy: 'claude-haiku-5-5', status: 'draft', createdAt: now() }
      drafts.push(draft)
      c.draftId = draft.draftId
      return draft
    }
    if (!seg[4]) return list(drafts, query, { filters: { status: 'status', kind: 'kind' } })
    const d = found(draftById(seg[4]), 'ese borrador')
    if (method === 'PUT') return Object.assign(d, await readBody())
    if (seg[5] === 'send' || seg[5] === 'manual') {
      d.status = seg[5] === 'send' ? 'sent' : 'manual'
      human.outbox.push({ draftId: d.draftId, status: d.status, subject: d.subject, body: d.body, to: d.to, attachments: d.attachments, by: 'tesoreria@valtermia.example', at: now() })
      return d
    }
    return d
  }

  if (resource === 'memory-rules') {
    if (method === 'GET') return human.memoryRules.filter((r) => r.active)
    if (method === 'POST') {
      const rule = { ruleId: `MR-${String(human.memoryRules.length + 1).padStart(4, '0')}`, active: true, at: now(), ...(await readBody()) }
      human.memoryRules.push(rule)
      return rule
    }
    if (method === 'DELETE') {
      found(human.memoryRules.find((r) => r.ruleId === seg[4]), 'esa regla').active = false
      return null
    }
  }

  if (resource === 'open-items') {
    let rows = openItems
    if (query.get('overdue') === 'true') rows = rows.filter((i) => i.daysOverdue > 0 && i.openAtEndCents > 0)
    return list(rows, query, { search: (r) => [r.itemId, r.documentNumber, r.partyName], filters: { entity: 'entity', partyId: 'partyId', status: 'status', type: 'itemType' } })
  }
  if (resource === 'aging') return aging(query.get('entity'), query.get('partyKind') ?? 'customer')
  if (resource === 'parties') {
    const party = found(partyById.get(seg[4]), 'ese tercero')
    const own = factByTxnsOf(party.partyId)
    return {
      party, group: party.groupId ? parties.filter((p) => p.groupId === party.groupId && p.partyId !== party.partyId).map(({ partyId, name, entity }) => ({ partyId, name, entity })) : [],
      items: openItems.filter((i) => i.partyId === party.partyId).slice(0, 200), transactions: own.slice(0, 200).map(txnRow), cases: cases.filter((c) => c.partyId === party.partyId).map(caseRow),
    }
  }
  throw new Problem(404, 'Ruta desconocida')
}
const factByTxnsOf = (partyId) => txns.filter((t) => factByTxn.get(t.bankTxnId)?.partyId === partyId)

createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost')
  const readBody = (raw) => new Promise((resolve) => {
    const chunks = []
    req.on('data', (c) => chunks.push(c))
    req.on('end', () => resolve(raw ? Buffer.concat(chunks) : JSON.parse(Buffer.concat(chunks).toString() || '{}')))
  })
  const send = (status, body, type = 'application/json') => {
    res.writeHead(status, { 'Content-Type': type, 'Access-Control-Allow-Origin': '*' })
    res.end(body == null ? '' : JSON.stringify(body))
  }
  try {
    const result = await route(req.method, url.pathname, url.searchParams, readBody)
    send(result === null ? 204 : 200, result)
  } catch (e) {
    const status = e.status ?? 500
    if (status === 500) console.error(e)
    send(status, { title: status === 404 ? 'Not Found' : 'Error', status, detail: e.message }, 'application/problem+json')
  }
}).listen(PORT, () => console.log(`mock API en http://localhost:${PORT} · ${txns.length} movimientos · ${run.runId}`))
