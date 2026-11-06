import { Page, PageHeader, EmptyState } from '@/components'

export function ExplorerPage() {
  return (
    <Page>
      <PageHeader title="Explorador" subtitle="Partidas, terceros, documentos y ficheros de detalle del paquete." />
      <EmptyState title="Pantalla en construcción" />
    </Page>
  )
}
