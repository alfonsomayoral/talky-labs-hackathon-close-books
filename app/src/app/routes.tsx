import { lazy, Suspense, type ComponentType, type LazyExoticComponent } from 'react'
import type { RouteObject } from 'react-router'
import { ButtonLink, EmptyState, Page, Skeleton } from '@/components'
import { SCREENS, type Screen } from '@/data'
import { AppShell } from '@/shell/AppShell'
import { RunGate } from '@/shell/RunGate'

// Each screen is its own chunk: the app opens fast whatever the size of the others.
const PAGES: Record<Screen['id'], LazyExoticComponent<ComponentType>> = {
  overview: lazy(() => import('@/features/overview/OverviewPage').then((m) => ({ default: m.OverviewPage }))),
  inbox: lazy(() => import('@/features/inbox/InboxPage').then((m) => ({ default: m.InboxPage }))),
  reconciliation: lazy(() => import('@/features/reconciliation/ReconciliationPage').then((m) => ({ default: m.ReconciliationPage }))),
  collections: lazy(() => import('@/features/collections/CollectionsPage').then((m) => ({ default: m.CollectionsPage }))),
  suppliers: lazy(() => import('@/features/suppliers/SuppliersPage').then((m) => ({ default: m.SuppliersPage }))),
  accounts: lazy(() => import('@/features/accounts/AccountsPage').then((m) => ({ default: m.AccountsPage }))),
  explorer: lazy(() => import('@/features/explorer/ExplorerPage').then((m) => ({ default: m.ExplorerPage }))),
  memory: lazy(() => import('@/features/memory/MemoryPage').then((m) => ({ default: m.MemoryPage }))),
  runs: lazy(() => import('@/features/runs/RunsPage').then((m) => ({ default: m.RunsPage }))),
}

const loading = (
  <Page>
    <Skeleton height={32} width={240} />
    <Skeleton height={240} />
  </Page>
)

function screenElement(screen: Screen) {
  const Component = PAGES[screen.id]
  const page = (
    <Suspense fallback={loading}>
      <Component />
    </Suspense>
  )
  return screen.worksWithoutRun ? page : <RunGate>{page}</RunGate>
}

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    children: [
      ...SCREENS.map((s) => ({ path: s.path, element: screenElement(s) })),
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
