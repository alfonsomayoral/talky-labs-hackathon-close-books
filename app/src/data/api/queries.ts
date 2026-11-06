// One hook per API resource (CONTRACT.md §5). Views use these, never the client.
import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'
import type {
  Account,
  Aging,
  CaseDecisionAction,
  CaseDetail,
  CaseRow,
  DataItem,
  DetailFileRow,
  DocumentDetail,
  DocumentRow,
  Draft,
  MemoryRule,
  OpenItem,
  Paged,
  Party,
  PartyDetail,
  Question,
  Run,
  RunStats,
  RunStatus,
  RunSummary,
  TxnDetail,
  TxnRow,
  UploadResult,
  ValidationResult,
} from '@/domain'
import { del, encodePath, get, post, postFile, put, type QueryParams } from './client'

/** The API's maximum page size (CONTRACT.md §5). */
export const PAGE_SIZE = 200

/** Who signs what a person does in the platform: there is no login. */
export const ACTOR = 'tesoreria@valtermia.example'

const run = (runId: string) => `/api/runs/${encodeURIComponent(runId)}`
const data = (phase: string) => `/api/data/${encodeURIComponent(phase)}`

/** All the pages loaded so far, flattened, plus what a virtualized table needs to ask for more. */
export interface PagedList<T> {
  rows: T[]
  total: number | null
  loading: boolean
  error: Error | null
  loadMore: () => void
  loadingMore: boolean
  refetch: () => void
}

/** Infinite list over a paged endpoint. Keeps the previous rows while a new filter loads. */
export function usePagedList<T>(path: string | null, params: QueryParams = {}, size = PAGE_SIZE): PagedList<T> {
  const q = useInfiniteQuery({
    queryKey: [path, params, size],
    enabled: path != null,
    initialPageParam: 1,
    queryFn: ({ pageParam, signal }) => get<Paged<T>>(path!, { size, ...params, page: pageParam }, signal),
    getNextPageParam: (last) => (last.page * last.size < last.total ? last.page + 1 : undefined),
    placeholderData: keepPreviousData,
  })
  const rows = useMemo(() => q.data?.pages.flatMap((p) => p.items) ?? [], [q.data])
  return {
    rows,
    total: q.data?.pages[0]?.total ?? null,
    loading: q.isPending && path != null,
    error: q.error,
    loadMore: () => {
      if (q.hasNextPage && !q.isFetchingNextPage) void q.fetchNextPage()
    },
    loadingMore: q.isFetchingNextPage,
    refetch: () => void q.refetch(),
  }
}

// ── Runs ─────────────────────────────────────────────────────────────────────

export const useRuns = () => useQuery({ queryKey: ['/api/runs'], queryFn: ({ signal }) => get<RunSummary[]>('/api/runs', undefined, signal) })

export const useRun = (runId: string | null) =>
  useQuery({ queryKey: [run(runId ?? ''), 'run'], enabled: runId != null, queryFn: ({ signal }) => get<Run>(run(runId!), undefined, signal) })

export const useRunStats = (runId: string | null, entity: string | null) =>
  useQuery({
    queryKey: [run(runId ?? ''), 'stats', entity],
    enabled: runId != null,
    queryFn: ({ signal }) => get<RunStats>(`${run(runId!)}/stats`, { entity }, signal),
    placeholderData: keepPreviousData,
  })

/** Polls while the run is in progress. */
export const useRunStatus = (runId: string | null) =>
  useQuery({
    queryKey: [run(runId ?? ''), 'status'],
    enabled: runId != null,
    queryFn: ({ signal }) => get<RunStatus>(`${run(runId!)}/status`, undefined, signal),
    refetchInterval: (q) => (q.state.data?.status === 'done' || q.state.data?.status === 'failed' ? false : 2000),
  })

export function useStartRun() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { phase: string; memoryFrom?: string }) => post<{ runId: string; status: string }>('/api/runs', body),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['/api/runs'] }),
  })
}

export const useValidateRun = () => useMutation({ mutationFn: (runId: string) => post<ValidationResult>(`${run(runId)}/validate`) })
export const useUpload = () => useMutation({ mutationFn: (file: File) => postFile<UploadResult>('/api/uploads', file) })

// ── Transactions ─────────────────────────────────────────────────────────────

export const useTransactions = (runId: string | null, params: QueryParams) => usePagedList<TxnRow>(runId && `${run(runId)}/transactions`, params)

export const useTransaction = (runId: string | null, bankTxnId: string | null) =>
  useQuery({
    queryKey: [run(runId ?? ''), 'transaction', bankTxnId],
    enabled: runId != null && bankTxnId != null,
    queryFn: ({ signal }) => get<TxnDetail>(`${run(runId!)}/transactions/${encodeURIComponent(bankTxnId!)}`, undefined, signal),
  })

// ── Cases, questions and drafts ──────────────────────────────────────────────

export const useCases = (runId: string | null, params: QueryParams) => usePagedList<CaseRow>(runId && `${run(runId)}/cases`, params)

export const useCase = (runId: string | null, caseId: string | null) =>
  useQuery({
    queryKey: [run(runId ?? ''), 'case', caseId],
    enabled: runId != null && caseId != null,
    queryFn: ({ signal }) => get<CaseDetail>(`${run(runId!)}/cases/${encodeURIComponent(caseId!)}`, undefined, signal),
  })

export const useQuestions = (runId: string | null, status?: Question['status']) => usePagedList<Question>(runId && `${run(runId)}/questions`, { status })
export const useDrafts = (runId: string | null, status?: Draft['status']) => usePagedList<Draft>(runId && `${run(runId)}/drafts`, { status })

/** Anything a person writes can move counts anywhere in the run: refresh everything of that run. */
const refreshRun = (client: QueryClient, runId: string) =>
  client.invalidateQueries({ predicate: (q) => typeof q.queryKey[0] === 'string' && q.queryKey[0].startsWith(run(runId)) })

export function useDecideCase(runId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (v: { caseId: string; action: CaseDecisionAction; note?: string }) =>
      post<CaseDetail>(`${run(runId)}/cases/${encodeURIComponent(v.caseId)}/decision`, { action: v.action, note: v.note ?? '', by: ACTOR }),
    onSuccess: () => refreshRun(client, runId),
  })
}

export function useAnswerQuestion(runId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (v: { questionId: string; optionId: string; note?: string; saveAsRule: boolean }) =>
      post<CaseDetail>(`${run(runId)}/questions/${encodeURIComponent(v.questionId)}/answer`, {
        optionId: v.optionId,
        note: v.note ?? '',
        saveAsRule: v.saveAsRule,
        by: ACTOR,
      }),
    onSuccess: () => refreshRun(client, runId),
  })
}

const draftPath = (runId: string, draftId: string) => `${run(runId)}/drafts/${encodeURIComponent(draftId)}`

export function useDraftActions(runId: string) {
  const client = useQueryClient()
  const onSuccess = () => refreshRun(client, runId)
  return {
    create: useMutation({ mutationFn: (v: { caseId: string; kind: Draft['kind'] }) => post<Draft>(`${run(runId)}/drafts`, v), onSuccess }),
    save: useMutation({
      mutationFn: (v: { draftId: string; subject: string; body: string }) => put<Draft>(draftPath(runId, v.draftId), { subject: v.subject, body: v.body }),
      onSuccess,
    }),
    send: useMutation({ mutationFn: (draftId: string) => post<Draft>(`${draftPath(runId, draftId)}/send`), onSuccess }),
    manual: useMutation({ mutationFn: (draftId: string) => post<Draft>(`${draftPath(runId, draftId)}/manual`), onSuccess }),
  }
}

// ── Memory ───────────────────────────────────────────────────────────────────

export const useMemoryRules = (runId: string | null) =>
  useQuery({
    queryKey: [run(runId ?? ''), 'memory-rules'],
    enabled: runId != null,
    queryFn: ({ signal }) => get<MemoryRule[]>(`${run(runId!)}/memory-rules`, undefined, signal),
  })

export function useMemoryRuleActions(runId: string) {
  const client = useQueryClient()
  const onSuccess = () => refreshRun(client, runId)
  return {
    create: useMutation({
      mutationFn: (v: Pick<MemoryRule, 'kind' | 'params' | 'description' | 'scope' | 'createdFrom'>) =>
        post<MemoryRule>(`${run(runId)}/memory-rules`, { ...v, by: ACTOR }),
      onSuccess,
    }),
    remove: useMutation({ mutationFn: (ruleId: string) => del<void>(`${run(runId)}/memory-rules/${encodeURIComponent(ruleId)}`), onSuccess }),
  }
}

// ── Open items, aging and parties ────────────────────────────────────────────

export const useOpenItems = (runId: string | null, params: QueryParams) => usePagedList<OpenItem>(runId && `${run(runId)}/open-items`, params)

export const useAging = (runId: string | null, entity: string | null, partyKind: Party['kind']) =>
  useQuery({
    queryKey: [run(runId ?? ''), 'aging', entity, partyKind],
    enabled: runId != null,
    queryFn: ({ signal }) => get<Aging>(`${run(runId!)}/aging`, { entity, partyKind }, signal),
    placeholderData: keepPreviousData,
  })

export const useParty = (runId: string | null, partyId: string | null) =>
  useQuery({
    queryKey: [run(runId ?? ''), 'party', partyId],
    enabled: runId != null && partyId != null,
    queryFn: ({ signal }) => get<PartyDetail>(`${run(runId!)}/parties/${encodeURIComponent(partyId!)}`, undefined, signal),
  })

// ── Package data ─────────────────────────────────────────────────────────────

export const useAccounts = (phase: string | null, runId: string | null) =>
  useQuery({
    queryKey: [data(phase ?? ''), 'accounts', runId],
    enabled: phase != null,
    queryFn: ({ signal }) => get<Account[]>(`${data(phase!)}/accounts`, { runId }, signal),
  })

export const useDataItems = (phase: string | null, params: QueryParams) => usePagedList<DataItem>(phase && `${data(phase)}/items`, params)
export const useDataParties = (phase: string | null, params: QueryParams) => usePagedList<Party>(phase && `${data(phase)}/parties`, params)
export const useDataDocuments = (phase: string | null, params: QueryParams) => usePagedList<DocumentRow>(phase && `${data(phase)}/documents`, params)
export const useDetailFiles = (phase: string | null, params: QueryParams) => usePagedList<DetailFileRow>(phase && `${data(phase)}/detail-files`, params)

export const useDocument = (phase: string | null, path: string | null) =>
  useQuery({
    queryKey: [data(phase ?? ''), 'document', path],
    enabled: phase != null && path != null,
    queryFn: ({ signal }) => get<DocumentDetail>(`${data(phase!)}/documents/${encodePath(path!)}`, undefined, signal),
  })
