import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { CloudOff } from 'lucide-react'
import { Amount, Badge, EmptyState, KeyValue, Mono, Section, Skeleton, type KeyValueItem } from '@/components'
import { useDataItems, useDocument, useParty } from '@/data'
import { CASE_STATUS_LABEL, CASE_STATUS_TONE, caseKindLabel, type OpenItem } from '@/domain'
import { formatDate } from '@/lib/format'
import { useScopedTo } from '@/lib/urlState'
import { facetLabel } from './facetLabel'
import { MiniTable } from './MiniTable'
import { clauseText, factExtras, withParams } from './model'
import styles from './panels.module.css'

export interface PanelProps {
  id: string
  phase: string
  runId: string
}

const ITEM_STATUS_LABEL: Record<OpenItem['status'], string> = {
  open: 'Abierta',
  partial: 'Parcial',
  cleared: 'Liquidada',
  disputed: 'En disputa',
  returned: 'Devuelta',
}

function Loaded({ loading, error, children }: { loading: boolean; error: Error | null; children: ReactNode }) {
  if (loading || error) {
    return (
      <div className={styles.body}>
        {loading ? <Skeleton lines={6} /> : <EmptyState size="sm" icon={<CloudOff />} title="No se ha podido cargar" description={error?.message} />}
      </div>
    )
  }
  return children
}

const heading = (kind: string, title: ReactNode, id: string) => (
  <div className={styles.head}>
    <span className={styles.kind}>{kind}</span>
    <h2 className={styles.title}>{title}</h2>
    <Mono muted>{id}</Mono>
  </div>
)

function usePartyLink() {
  const scoped = useScopedTo()
  return (partyId: string) => withParams(scoped('/explorador'), { tipo: 'parties', ver: partyId })
}

export function ItemPanel({ id, phase }: PanelProps) {
  const found = useDataItems(phase, { q: id })
  const partyLink = usePartyLink()
  const item = found.rows.find((i) => i.itemId === id)
  return (
    <Loaded loading={found.loading} error={found.error}>
      {item ? (
        <div className={styles.body}>
          {heading(facetLabel('items', item.itemType), <Mono>{item.documentNumber}</Mono>, item.itemId)}
          <KeyValue
            items={[
              {
                label: 'Tercero',
                value: (
                  <Link className={styles.link} to={partyLink(item.partyId)}>
                    {item.partyName}
                  </Link>
                ),
              },
              { label: 'Sociedad', value: item.entity, mono: true },
              { label: 'Emisión', value: formatDate(item.issueDate) },
              { label: 'Vencimiento', value: formatDate(item.dueDate) },
              { label: 'Total', value: <Amount cents={item.totalCents} currency={item.currency} /> },
              { label: 'Abierta al inicio', value: <Amount cents={item.openAtStartCents} currency={item.currency} /> },
              { label: 'Documento relacionado', value: item.relatedDocument, mono: true },
              { label: 'Referencia', value: item.reference, mono: true },
            ]}
          />
        </div>
      ) : (
        <div className={styles.body}>
          <EmptyState size="sm" title="No existe esa partida" description="Puede que sea de otra fase." />
        </div>
      )}
    </Loaded>
  )
}

export function PartyPanel({ id, runId }: PanelProps) {
  const q = useParty(runId, id)
  const scoped = useScopedTo()
  const partyLink = usePartyLink()
  const d = q.data
  return (
    <Loaded loading={q.isPending} error={q.error}>
      {d && (
        <div className={styles.body}>
          {heading(facetLabel('parties', d.party.kind), d.party.name, d.party.partyId)}
          <KeyValue
            items={[
              { label: 'Nombre comercial', value: d.party.tradeName },
              { label: 'Sociedad', value: d.party.entity, mono: true },
              { label: 'NIF', value: d.party.taxId, mono: true },
              { label: 'IBAN', value: d.party.iban, mono: true },
              { label: 'País', value: d.party.country },
              { label: 'Condiciones', value: d.party.paymentTerms },
              { label: 'Divisa', value: d.party.currency, mono: true },
              { label: 'Bloqueado desde', value: d.party.blockedSince ? <Badge tone="danger">{formatDate(d.party.blockedSince)}</Badge> : null },
            ] satisfies KeyValueItem[]}
          />

          {(d.party.parentId || d.group.length > 0) && (
            <Section title="Grupo y matriz" count={d.group.length}>
              <ul className={styles.group}>
                {d.group.map((m) => (
                  <li key={m.partyId}>
                    <Link className={styles.link} to={partyLink(m.partyId)}>
                      {m.name}
                    </Link>
                    <Mono muted>{m.entity}</Mono>
                    {m.partyId === d.party.parentId && <Badge variant="outline">Matriz</Badge>}
                  </li>
                ))}
                {d.party.parentId && !d.group.some((m) => m.partyId === d.party.parentId) && (
                  <li>
                    <Link className={styles.link} to={partyLink(d.party.parentId)}>
                      <Mono>{d.party.parentId}</Mono>
                    </Link>
                    <Badge variant="outline">Matriz</Badge>
                  </li>
                )}
              </ul>
            </Section>
          )}

          <Section title="Partidas" count={d.items.length} description="Las primeras 200 por vencimiento.">
            {d.items.length === 0 ? (
              <p className={styles.none}>Sin partidas.</p>
            ) : (
              <MiniTable
                aria-label="Partidas del tercero"
                rows={d.items}
                getKey={(i) => i.itemId}
                columns={[
                  { header: 'Documento', width: '120px', cell: (i) => <Mono>{i.documentNumber}</Mono> },
                  { header: 'Vence', width: '96px', cell: (i) => formatDate(i.dueDate) },
                  { header: 'Estado', width: '84px', cell: (i) => ITEM_STATUS_LABEL[i.status] },
                  { header: 'Pendiente', align: 'right', cell: (i) => <Amount cents={i.openAtEndCents} currency={i.currency} /> },
                ]}
              />
            )}
          </Section>

          <Section title="Movimientos" count={d.transactions.length} description="Los últimos 200.">
            {d.transactions.length === 0 ? (
              <p className={styles.none}>Sin movimientos en la fase.</p>
            ) : (
              <MiniTable
                aria-label="Movimientos del tercero"
                rows={d.transactions}
                getKey={(t) => t.bankTxnId}
                rowTo={(t) => withParams(scoped('/conciliacion'), { ver: t.bankTxnId })}
                columns={[
                  { header: 'Fecha', width: '96px', cell: (t) => formatDate(t.bookingDate) },
                  { header: 'Concepto', cell: (t) => t.text },
                  { header: 'Importe', width: '120px', align: 'right', cell: (t) => <Amount cents={t.amountCents} currency={t.currency} /> },
                ]}
              />
            )}
          </Section>

          <Section title="Casos" count={d.cases.length}>
            {d.cases.length === 0 ? (
              <p className={styles.none}>Sin casos.</p>
            ) : (
              <MiniTable
                aria-label="Casos del tercero"
                rows={d.cases}
                getKey={(c) => c.caseId}
                rowTo={(c) => withParams(scoped('/bandeja'), { ver: c.caseId })}
                columns={[
                  { header: 'Caso', cell: (c) => caseKindLabel(c.kind) },
                  { header: 'Estado', width: '110px', cell: (c) => <Badge tone={CASE_STATUS_TONE[c.status]}>{CASE_STATUS_LABEL[c.status]}</Badge> },
                  { header: 'Importe', width: '120px', align: 'right', cell: (c) => <Amount cents={c.amountCents} currency={c.currency} /> },
                ]}
              />
            )}
          </Section>
        </div>
      )}
    </Loaded>
  )
}

export function DocumentPanel({ id, phase }: PanelProps) {
  const q = useDocument(phase, id)
  const d = q.data
  const clauses = d?.facts.filter((f) => f.clause) ?? []
  const facts = d?.facts.filter((f) => !f.clause) ?? []
  return (
    <Loaded loading={q.isPending} error={q.error}>
      {d && (
        <div className={styles.body}>
          {heading(facetLabel('documents', d.kind), d.name, d.path)}
          <KeyValue
            items={[
              { label: 'Sociedad', value: d.entity, mono: true },
              { label: 'Formato', value: d.format, mono: true },
              { label: 'Fecha', value: formatDate(d.date) },
              { label: d.kind === 'remittanceAdvice' ? 'Pagador' : 'Tercero', value: d.partyName },
            ]}
          />

          {clauses.length > 0 && (
            <Section title="Cláusulas extraídas" count={clauses.length}>
              <ul className={styles.facts}>
                {clauses.map((f, i) => (
                  <li key={i} className={styles.fact}>
                    {clauseText(f.clause!, f.clauseValue)}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {(facts.length > 0 || clauses.length === 0) && (
            <Section title="Hechos extraídos" count={facts.length}>
              {facts.length === 0 ? (
                <p className={styles.none}>No se ha extraído ningún hecho de este documento.</p>
              ) : (
                <ul className={styles.facts}>
                  {facts.map((f, i) => (
                    <li key={i} className={styles.fact}>
                      <div className={styles.factMain}>
                        <Mono>{f.documentNumber ?? '—'}</Mono>
                        <Badge variant="outline" title={f.model ?? undefined}>
                          {f.method === 'model' ? `modelo${f.model ? ` · ${f.model}` : ''}` : 'parser'}
                        </Badge>
                      </div>
                      <div className={styles.factAmounts}>
                        <span>
                          Pagado <Amount cents={f.paidCents} currency={f.currency ?? undefined} />
                        </span>
                        <span>
                          Bruto <Amount cents={f.grossCents} currency={f.currency ?? undefined} />
                        </span>
                        <span>
                          Deducción <Amount cents={f.deductionCents} currency={f.currency ?? undefined} />
                          {f.reason ? ` (${f.reason})` : ''}
                        </span>
                      </div>
                      {factExtras(f).length > 0 && <p className={styles.extras}>{factExtras(f).join(' · ')}</p>}
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          )}

          <Section title="Texto extraído">
            {d.text ? <pre className={styles.text}>{d.text}</pre> : <p className={styles.none}>Este documento no tiene texto extraído.</p>}
          </Section>
        </div>
      )}
    </Loaded>
  )
}
