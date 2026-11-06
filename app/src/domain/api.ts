// Response shapes of the API, generated from backend/openapi.json: `npm run gen:api` rewrites api.generated.ts.
// Views import these names, so a change in the schema shows up here as a type error, not as a broken screen.
import type { components } from './api.generated'
import type { CasePriority, RulePreview, Score } from './run'

type Schemas = components['schemas']

export interface Paged<T> {
  items: T[]
  total: number
  page: number
  size: number
}

export type RunSummary = Schemas['RunSummary']
export type EntityStats = Schemas['EntityStats']
export type DayStats = Schemas['DayStats']
/** The schema leaves the scorer's metrics and segments untyped. */
export type RunStats = Omit<Schemas['RunStats'], 'score'> & { score: Score | null }
export type RunStatus = Schemas['RunStatus']
/** The schema's `errors` point at FastAPI's own ValidationError by a name clash: CONTRACT.md §5.1 is what it sends. */
export type ValidationResult = Omit<Schemas['ValidationResult'], 'errors'> & { errors: { row: number | null; message: string }[] }
export type UploadResult = Schemas['UploadResult']
export type Assignment = Schemas['Assignment']
export type TxnRow = Schemas['TxnRow']
export type BankLine = Schemas['BankLine']
export type ItemSummary = Schemas['ItemSummary']
export type DetailRow = Schemas['DetailRow']
export type PartyResolution = Schemas['PartyResolution']
export type DocumentFact = Schemas['DocumentFact']
export type Evidence = Schemas['Evidence']
export type RelatedTxn = Schemas['RelatedTxn']
export type TxnDetail = Schemas['TxnDetail']
export type CaseRow = Omit<Schemas['CaseRow'], 'priority'> & { priority: CasePriority }
export type Question = Omit<Schemas['Question'], 'rulePreview'> & { rulePreview?: RulePreview | null }
export type Draft = Schemas['Draft']
export type CaseDetail = Omit<Schemas['CaseDetail'], 'priority' | 'question'> & { priority: CasePriority; question?: Question | null }
export type ItemHistoryEntry = Schemas['ItemHistoryEntry']
export type OpenItem = Schemas['OpenItem']
export type AgingParty = Omit<Schemas['AgingParty'], 'buckets'> & { buckets: Record<AgingBucket, number> }
export type Aging = Omit<Schemas['Aging'], 'totals' | 'parties'> & { totals: Record<AgingBucket, number>; parties: AgingParty[] }
export type Party = Schemas['Party']
export type PartyDetail = Schemas['PartyDetail']
export type Account = Schemas['Account']
export type DataItem = Schemas['DataItem']
export type DocumentRow = Schemas['DocumentRow']
export type DocumentDetail = Schemas['DocumentDetail']
export type DetailFileRow = Schemas['DetailFileRow']

export type RunState = RunStatus['status']
export type EvidenceContent = Evidence['content']

/** Keys of `Aging.totals` and `AgingParty.buckets`: the schema only says they are strings. */
export type AgingBucket = 'not_due' | 'd1_30' | 'd31_60' | 'd61_90' | 'd90_plus'
