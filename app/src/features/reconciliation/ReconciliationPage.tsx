import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { SearchX, CloudOff } from 'lucide-react'
import type { TxnRow } from '@/domain'
import { CASE_STATUS_LABEL, CASE_STATUS_EMPHASIS, evidenceOf, ruleDescription } from '@/domain'
import { Amount, Badge, ConfidenceBand, DataTable, EmptyState, FilterBar, FilterChip, Mono, Page, PageHeader, Skeleton, type Column } from '@/components'
import { useActiveRun, useAccounts, useRunStats, useTransactions } from '@/data'
import { formatDate, formatNumber } from '@/lib/format'
import { useEntityScope, useListParam, useOpenObject, useTextParam } from '@/lib/urlState'
import { TxnPanel } from '@/features/shared'
import { SearchBox } from './SearchBox'
import { buildFacetOptions, FACETS, hasActiveFilters, rowsCell, sortFromParam, sortToParam, toApiParams, type FacetKey, type Facets } from './model'
import styles from './ReconciliationPage.module.css'

const getRowId = (t: TxnRow) => t.bankTxnId

const COLUMNS: Column<TxnRow>[] = [
  { id: 'bookingDate', header: 'Fecha', width: 92, cell: (t) => <span className={styles.muted}>{formatDate(t.bookingDate)}</span>, sortValue: (t) => t.bookingDate },
  { id: 'entity', header: 'Sociedad', width: 96, cell: (t) => <Mono>{t.entity}</Mono>, sortValue: (t) => t.entity },
  { id: 'text', header: 'Texto del banco', width: 'minmax(160px, 2fr)', cell: (t) => <span className={styles.text} title={t.text}>{t.text}</span>, sortValue: (t) => t.text },
  { id: 'amountEur', header: 'Importe', width: 152, align: 'right', cell: (t) => <Amount cents={t.amountCents} currency={t.currency} signed colorize />, sortValue: (t) => t.amountEur },
  {
    id: 'rowCount',
    header: 'Partidas',
    width: 148,
    cell: (t) => {
      const { first, mono, extra } = rowsCell(t)
      if (first == null) return <span className={styles.muted}>—</span>
      return (
        <span className={styles.rows}>
          {mono ? <Mono>{first}</Mono> : <span className={styles.muted}>{first}</span>}
          {extra > 0 && <span className={styles.extra}>+{formatNumber(extra)}</span>}
        </span>
      )
    },
    sortValue: (t) => t.rowCount,
  },
  { id: 'evidence', header: 'Evidencia', width: 112, cell: (t) => <span className={styles.evidence}>{evidenceOf(t.rule).source}</span> },
  { id: 'rule', header: 'Regla', width: 168, cell: (t) => <Mono title={ruleDescription(t.rule)}>{t.rule}</Mono>, sortValue: (t) => t.rule },
  { id: 'confidence', header: 'Confianza', width: 104, cell: (t) => <ConfidenceBand value={t.confidence} />, sortValue: (t) => t.confidence },
  {
    id: 'caseStatus',
    header: 'Caso',
    width: 116,
    cell: (t) => (t.caseStatus ? <Badge emphasis={CASE_STATUS_EMPHASIS[t.caseStatus]}>{CASE_STATUS_LABEL[t.caseStatus]}</Badge> : <span className={styles.muted}>—</span>),
    sortValue: (t) => t.caseStatus,
  },
  // Last: the account is also a filter and the panel's header, so it is what falls off a narrow screen, not the rule.
  { id: 'accountId', header: 'Cuenta', width: 140, cell: (t) => <Mono>{t.accountId}</Mono>, sortValue: (t) => t.accountId },
]

export function ReconciliationPage() {
  const { runId, phase } = useActiveRun()
  const [entity] = useEntityScope()
  const [q, setQ] = useTextParam('q')
  const [orden, setOrden] = useTextParam('orden')
  const [ver, setVer] = useOpenObject()
  const [, setParams] = useSearchParams()
  const [cursor, setCursor] = useState<string | null>(null)

  const [entities, setEntities] = useListParam(FACETS.entity.param)
  const [accountIds, setAccountIds] = useListParam(FACETS.account.param)
  const [formats, setFormats] = useListParam(FACETS.format.param)
  const [rules, setRules] = useListParam(FACETS.rule.param)
  const [exceptions, setExceptions] = useListParam(FACETS.exception.param)
  const [categories, setCategories] = useListParam(FACETS.category.param)
  const [statuses, setStatuses] = useListParam(FACETS.status.param)
  const facets: Facets = { entity: entities, account: accountIds, format: formats, rule: rules, exception: exceptions, category: categories, status: statuses }
  const setFacet: Record<FacetKey, (next: string[]) => void> = {
    entity: setEntities,
    account: setAccountIds,
    format: setFormats,
    rule: setRules,
    exception: setExceptions,
    category: setCategories,
    status: setStatuses,
  }

  const sort = sortFromParam(orden)
  const filters = { q: q ?? '', entity, facets }
  const list = useTransactions(runId, toApiParams({ ...filters, sort }))
  const stats = useRunStats(runId, entity)
  const accounts = useAccounts(phase, runId)
  const options = useMemo(() => buildFacetOptions(stats.data, accounts.data, entity), [stats.data, accounts.data, entity])

  const clear = () =>
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('q')
      for (const { param } of Object.values(FACETS)) next.delete(param)
      return next
    })

  const chip = (key: FacetKey, label: string) => (
    <FilterChip key={key} label={label} options={options[key]} selected={facets[key]} onChange={setFacet[key]} />
  )

  return (
    <Page fill>
      <PageHeader
        title="Conciliación"
        subtitle="Qué liquida cada movimiento del banco y por qué: su regla, sus partidas y la evidencia que lo respalda."
        filters={
          <FilterBar
            onClear={hasActiveFilters(filters) ? clear : undefined}
            end={
              list.total != null && (
                <span className={styles.count}>
                  {formatNumber(list.total)} {list.total === 1 ? 'movimiento' : 'movimientos'}
                </span>
              )
            }
          >
            <SearchBox value={q ?? ''} onCommit={(v) => setQ(v.trim() || null)} placeholder="Buscar texto, contraparte, id o factura" aria-label="Buscar movimientos" />
            {!entity && chip('entity', 'Sociedad')}
            {chip('account', 'Cuenta')}
            {chip('format', 'Formato')}
            {chip('rule', 'Regla')}
            {chip('exception', 'Excepción')}
            {chip('category', 'Categoría')}
            {chip('status', 'Estado del caso')}
          </FilterBar>
        }
      />
      {list.error && list.rows.length === 0 ? (
        <EmptyState icon={<CloudOff />} title="No se pudieron cargar los movimientos" description={list.error.message} action={undefined} />
      ) : list.loading ? (
        <Skeleton height={320} />
      ) : (
        <DataTable
          aria-label="Movimientos bancarios"
          rows={list.rows}
          columns={COLUMNS}
          getRowId={getRowId}
          sort={sort}
          onSortChange={(next) => setOrden(sortToParam(next))}
          serverSort
          onEndReached={list.loadMore}
          selectedId={ver ?? cursor}
          onSelectedChange={(id) => {
            setCursor(id)
            if (ver && id) setVer(id)
          }}
          onOpen={(t) => setVer(t.bankTxnId)}
          globalKeys
          empty={<EmptyState icon={<SearchX />} size="sm" title="Ningún movimiento con estos filtros" description="Quita algún filtro o prueba con otra búsqueda." />}
        />
      )}
      {ver && <TxnPanel bankTxnId={ver} onClose={() => setVer(null)} />}
    </Page>
  )
}
