import { useMemo } from 'react'
import { useNavigate } from 'react-router'
import { CloudOff, Landmark } from 'lucide-react'
import { Amount, Badge, Card, EmptyState, Metric, Mono, Page, PageHeader, ProgressBar, Skeleton, DataTable, type Column } from '@/components'
import { useAccounts, useActiveRun } from '@/data'
import { statementFormatLabel, type Account } from '@/domain'
import { formatNumber, formatPercent } from '@/lib/format'
import { useEntityScope, useScopedTo } from '@/lib/urlState'
import { currentFormat, filterByEntity, formatChange, summarize } from './model'
import styles from './AccountsPage.module.css'

const COLUMNS: Column<Account>[] = [
  {
    id: 'account',
    header: 'Cuenta',
    width: 'minmax(150px, 1.2fr)',
    cell: (a) => (
      <span className={styles.account}>
        <Mono>{a.accountId}</Mono>
        {!a.inMaster && (
          <Badge emphasis="medium" aria-label="No está en el maestro" title="No está en el maestro: aparece en los movimientos pero no en el maestro de cuentas">
            sin maestro
          </Badge>
        )}
      </span>
    ),
    sortValue: (a) => a.accountId,
  },
  { id: 'bank', header: 'Banco', width: 'minmax(136px, 1fr)', cell: (a) => <span className={styles.bank} title={a.bankName ?? a.bank}>{a.bankName ?? a.bank}</span>, sortValue: (a) => a.bankName ?? a.bank },
  { id: 'entity', header: 'Sociedad', width: 92, cell: (a) => <Mono>{a.entity}</Mono>, sortValue: (a) => a.entity },
  {
    id: 'format',
    header: 'Formato de extracto',
    width: 'minmax(290px, 1fr)',
    cell: (a) => {
      const change = formatChange(a.formats)
      return change ? (
        <Badge emphasis="medium" title="El banco migra sus extractos a otro formato durante la fase y los textos cambian de forma">
          {change}
        </Badge>
      ) : (
        <span>{statementFormatLabel(currentFormat(a.formats) ?? '—')}</span>
      )
    },
    sortValue: (a) => currentFormat(a.formats),
  },
  { id: 'txns', header: 'Movimientos', width: 112, align: 'right', cell: (a) => formatNumber(a.txns), sortValue: (a) => a.txns },
  {
    id: 'inflow',
    header: 'Entradas',
    width: 116,
    align: 'right',
    cell: (a) => <Amount cents={a.inflowCents} currency={a.currency} decimals={0} compact />,
    sortValue: (a) => a.inflowCents,
  },
  {
    id: 'outflow',
    header: 'Salidas',
    width: 116,
    align: 'right',
    cell: (a) => <Amount cents={a.outflowCents} currency={a.currency} decimals={0} compact />,
    sortValue: (a) => a.outflowCents,
  },
  {
    id: 'net',
    header: 'Neto',
    width: 116,
    align: 'right',
    cell: (a) => <Amount cents={a.netCents} currency={a.currency} decimals={0} compact />,
    sortValue: (a) => a.netCents,
  },
  {
    id: 'reconciled',
    header: '% conciliado',
    width: 118,
    cell: (a) =>
      a.reconciledRate == null ? (
        '—'
      ) : (
        <span className={styles.rate}>
          <ProgressBar value={a.reconciledRate} size="sm" label={`${a.accountId} conciliada`} className={styles.bar} />
          <span className="tabular">{formatPercent(a.reconciledRate)}</span>
        </span>
      ),
    sortValue: (a) => a.reconciledRate,
  },
]

export function AccountsPage() {
  const { phase, runId } = useActiveRun()
  const accounts = useAccounts(phase, runId)
  const [entity] = useEntityScope()
  const scoped = useScopedTo()
  const navigate = useNavigate()

  const rows = useMemo(() => filterByEntity(accounts.data ?? [], entity), [accounts.data, entity])
  const summary = useMemo(() => summarize(rows), [rows])

  const open = (a: Account) => {
    const to = scoped('/conciliacion')
    const search = new URLSearchParams(to.search)
    search.set('cuenta', a.accountId)
    void navigate({ pathname: to.pathname, search: `?${search}` })
  }

  return (
    <Page fill>
      <PageHeader title="Cuentas bancarias" subtitle="Las cuentas del grupo, su formato, su neto y su conciliación. Pulsa una cuenta para ver sus movimientos." />
      <div className={styles.metrics}>
        <Card padding="sm">
          <Metric label="Cuentas" value={formatNumber(summary.accounts)} loading={accounts.isPending} />
        </Card>
        <Card padding="sm">
          <Metric label="Bancos" value={formatNumber(summary.banks)} loading={accounts.isPending} />
        </Card>
        <Card padding="sm">
          <Metric
            label="Con cambio de formato"
            value={formatNumber(summary.formatChanges)}
            hint="Cuentas cuyo extracto cambió de formato durante la fase: el parser tiene que aguantar los dos."
            loading={accounts.isPending}
          />
        </Card>
      </div>
      <Card padding="none" className={styles.tableCard}>
        {accounts.isPending ? (
          <div className={styles.loading}>
            <Skeleton lines={6} />
          </div>
        ) : accounts.error ? (
          <EmptyState icon={<CloudOff />} title="No se han podido cargar las cuentas" description={accounts.error.message} />
        ) : rows.length === 0 ? (
          <EmptyState icon={<Landmark />} title="Esta sociedad no tiene cuentas en la fase" description="Quita el filtro de sociedad para ver las del grupo." />
        ) : (
          <DataTable aria-label="Cuentas bancarias" rows={rows} columns={COLUMNS} getRowId={(a) => a.accountId} defaultSort={{ columnId: 'account', direction: 'asc' }} onOpen={open} globalKeys />
        )}
      </Card>
    </Page>
  )
}
