// Public API of the data layer. Views import from '@/data' only (CLAUDE.md §6).
import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, retry: 1, refetchOnWindowFocus: false } },
})

export { ApiError } from './api/client'
export * from './api/queries'
export { useCurrentRun, useActiveRun } from './currentRun'
export { SCREENS, SCREEN_SECTIONS, type Screen } from './registry/screens'
export { EXPLORER_SPECS, type ExplorerSpec } from './registry/explorer'
