import { Page, PageHeader, EmptyState } from '@/components'

export function OverviewPage() {
  return (
    <Page>
      <PageHeader title="Resumen" subtitle="El pulso de la fase: lo conciliado sin intervención, lo identificado y lo que queda en revisión." />
      <EmptyState title="Pantalla en construcción" />
    </Page>
  )
}
