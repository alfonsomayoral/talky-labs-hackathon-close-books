import { Page, PageHeader, EmptyState } from '@/components'

export function InboxPage() {
  return (
    <Page>
      <PageHeader title="Te necesitan" subtitle="Los casos que esperan a una persona, por prioridad e importe." />
      <EmptyState title="Pantalla en construcción" />
    </Page>
  )
}
