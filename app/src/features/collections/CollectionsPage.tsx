import { Page, PageHeader, EmptyState } from '@/components'

export function CollectionsPage() {
  return (
    <Page>
      <PageHeader title="Cobros" subtitle="Clientes con saldo vencido, disputas abiertas y duplicados a devolver." />
      <EmptyState title="Pantalla en construcción" />
    </Page>
  )
}
