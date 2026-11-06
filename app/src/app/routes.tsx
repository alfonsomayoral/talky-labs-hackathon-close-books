import type { RouteObject } from 'react-router'
import { ButtonLink, EmptyState, Page } from '@/components'
import { PAGE_VIEWS } from '@/data'
import { DatasetPage } from '@/features/dataset/DatasetPage'
import { EntitiesPage } from '@/features/entities/EntitiesPage'
import { ImportPage } from '@/features/import/ImportPage'
import { OverviewPage } from '@/features/overview/OverviewPage'
import { AppShell } from '@/shell/AppShell'

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    children: [
      { path: '/', element: <OverviewPage /> },
      ...PAGE_VIEWS.map((v) => ({ path: v.path!, element: v.kind === 'entities' ? <EntitiesPage /> : <DatasetPage key={v.kind} view={v} /> })),
      { path: '/importar', element: <ImportPage /> },
      {
        path: '*',
        element: (
          <Page>
            <EmptyState title="Esta página no existe" action={<ButtonLink to="/">Ir al resumen</ButtonLink>} />
          </Page>
        ),
      },
    ],
  },
]
