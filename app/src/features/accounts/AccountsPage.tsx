import { Page, PageHeader, EmptyState } from '@/components'

export function AccountsPage() {
  return (
    <Page>
      <PageHeader title="Cuentas bancarias" subtitle="Las cuentas del grupo, su formato, su saldo y su conciliación." />
      <EmptyState title="Pantalla en construcción" />
    </Page>
  )
}
