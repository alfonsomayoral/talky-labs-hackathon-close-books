// Screens that read a run only render once there is one; if not, this says why and what to do.
import type { ReactNode } from 'react'
import { useLocation } from 'react-router'
import { CloudOff, Play, SearchX } from 'lucide-react'
import { ButtonLink, EmptyState, Page, Skeleton } from '@/components'
import { useCurrentRun } from '@/data'
import { useRunParam } from '@/lib/urlState'

export function RunGate({ children }: { children: ReactNode }) {
  const { run, loading, error } = useCurrentRun()
  const [wanted] = useRunParam()
  const { pathname } = useLocation()
  if (loading) {
    return (
      <Page>
        <Skeleton height={32} width={240} />
        <Skeleton height={240} />
      </Page>
    )
  }
  if (error) {
    return (
      <Page>
        <EmptyState icon={<CloudOff />} title="No hay conexión con la API" description="Arranca closebooks serve o el servidor de prueba en el puerto 8000 y recarga." />
      </Page>
    )
  }
  if (!run) {
    return (
      <Page>
        {wanted ? (
          <EmptyState icon={<SearchX />} title={`No existe la ejecución ${wanted}`} action={<ButtonLink to={pathname}>Ver la última</ButtonLink>} />
        ) : (
          <EmptyState icon={<Play />} title="Todavía no hay ninguna ejecución" description="Lanza la primera desde la consola." action={<ButtonLink to="/ejecuciones">Ir a ejecuciones</ButtonLink>} />
        )}
      </Page>
    )
  }
  return children
}
