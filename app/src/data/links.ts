// Lookups and relations between the objects of a Dataset and the Run, built once per load.
import type { Alert, Dataset, DatasetKind, ErpEvent, Match, ObjectKind, ObjectRef, Run } from '@/domain'
import { KIND_OF } from '@/domain'

export type AnyObject = { id: string; entityId?: string }

export const refKey = (r: ObjectRef) => `${r.kind}:${r.id}`

export function parseRefKey(key: string): ObjectRef | null {
  const i = key.indexOf(':')
  if (i < 1) return null
  const kind = key.slice(0, i) as ObjectKind
  return Object.values(KIND_OF).includes(kind) ? { kind, id: key.slice(i + 1) } : null
}

export interface Links {
  get(ref: ObjectRef): AnyObject | undefined
  /** Alerts whose subject or evidence is this object. */
  alertsOf(ref: ObjectRef): Alert[]
  /** ERP events about this object, oldest first. */
  historyOf(ref: ObjectRef): ErpEvent[]
  matchOf(bankTransactionId: string): Match | undefined
  /** Objects directly linked to this one by id, through the Dataset or the Run's matches. */
  related(ref: ObjectRef): ObjectRef[]
}

function push<K, V>(map: Map<K, V[]>, key: K, value: V) {
  const list = map.get(key)
  if (list) list.push(value)
  else map.set(key, [value])
}

export function buildLinks(ds: Dataset, run: Run | null): Links {
  const byKey = new Map<string, AnyObject>()
  for (const kind of Object.keys(KIND_OF) as DatasetKind[]) {
    for (const o of ds[kind] as AnyObject[]) byKey.set(`${KIND_OF[kind]}:${o.id}`, o)
  }
  const alerts = new Map<string, Alert[]>()
  for (const a of run?.alerts ?? []) for (const r of [a.subject, ...a.evidence]) push(alerts, refKey(r), a)
  const history = new Map<string, ErpEvent[]>()
  for (const e of [...ds.erpEvents].sort((a, b) => a.at.localeCompare(b.at))) push(history, refKey(e.subject), e)
  const matches = new Map((run?.matches ?? []).map((m) => [m.bankTransactionId, m]))

  const edges = new Map<string, ObjectRef[]>()
  const link = (a: ObjectRef, b: ObjectRef) => {
    if (!byKey.has(refKey(a)) || !byKey.has(refKey(b))) return
    push(edges, refKey(a), b)
    push(edges, refKey(b), a)
  }
  const vendor = (id: string | null) => (id ? { kind: 'vendor' as const, id } : null)
  for (const c of ds.contracts) if (c.vendorId) link({ kind: 'contract', id: c.id }, vendor(c.vendorId)!)
  for (const p of ds.purchaseOrders) {
    link({ kind: 'purchaseOrder', id: p.id }, vendor(p.vendorId)!)
    if (p.contractId) link({ kind: 'purchaseOrder', id: p.id }, { kind: 'contract', id: p.contractId })
  }
  for (const i of ds.invoices) {
    link({ kind: 'invoice', id: i.id }, vendor(i.vendorId)!)
    if (i.purchaseOrderId) link({ kind: 'invoice', id: i.id }, { kind: 'purchaseOrder', id: i.purchaseOrderId })
  }
  for (const l of ds.ledgerEntries) {
    if (!l.sourceRef) continue
    for (const kind of ['invoice', 'bankTransaction'] as const) link({ kind: 'ledgerEntry', id: l.id }, { kind, id: l.sourceRef })
  }
  for (const m of matches.values()) for (const t of m.targets) link({ kind: 'bankTransaction', id: m.bankTransactionId }, t)

  return {
    get: (r) => byKey.get(refKey(r)),
    alertsOf: (r) => alerts.get(refKey(r)) ?? [],
    historyOf: (r) => history.get(refKey(r)) ?? [],
    matchOf: (id) => matches.get(id),
    related: (r) => {
      const seen = new Set<string>()
      return (edges.get(refKey(r)) ?? []).filter((x) => !seen.has(refKey(x)) && seen.add(refKey(x)))
    },
  }
}
