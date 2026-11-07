"""Bodies of CONTRACT §5.1. Field names are the JSON keys (camelCase), so openapi.json carries them."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CaseStatus = Literal["auto", "needs_review", "question", "fallback", "done"]
ItemType = Literal["ARI", "ARC", "API", "APC"]
AgingBucket = Literal["not_due", "d1_30", "d31_60", "d61_90", "d90_plus"]


class Paged[T](BaseModel):
    items: list[T]
    total: int
    page: int
    size: int


# ── §2 shared ────────────────────────────────────────────────────────────────

class SourceRef(BaseModel):
    kind: str
    ref: str
    label: str | None = None


class Candidate(BaseModel):
    itemId: str
    amountCents: int
    currency: str
    why: str


class Explanation(BaseModel):
    bankTxnId: str
    itemId: str | None
    amountCents: int | None
    currency: str | None
    category: str | None
    exception: str | None
    rule: str
    confidence: float
    partyId: str | None
    reference: str | None
    sources: list[SourceRef]
    candidates: list[Candidate]


class Score(BaseModel):
    score: float
    metrics: dict
    segments: dict


class ModelUsage(BaseModel):
    calls: int
    inputTokens: int
    outputTokens: int
    costUsd: float


class Run(BaseModel):
    runId: str
    phase: str
    dataDir: str
    createdAt: str
    gitCommit: str | None
    durationMs: int
    stages: dict[str, int]
    txns: int
    rows: int
    csvBytes: int
    byRule: dict[str, int]
    byException: dict[str, int]
    byCategory: dict[str, int]
    cases: dict[str, int]
    models: dict[str, ModelUsage]
    memoryRulesApplied: int
    score: Score | None


class RunSummary(BaseModel):
    runId: str
    phase: str
    createdAt: str
    gitCommit: str | None
    durationMs: int
    txns: int
    rows: int
    cases: dict[str, int]
    memoryRulesApplied: int
    modelCalls: int
    modelCostUsd: float
    score: float | None
    served: bool


class Case(BaseModel):
    caseId: str
    kind: str
    status: CaseStatus
    priority: int
    entity: str
    bankTxnId: str | None
    partyId: str | None
    itemIds: list[str]
    amountCents: int
    currency: str
    amountEur: int
    bookingDate: str | None
    summary: str
    suggestedAction: str
    questionId: str | None
    draftId: str | None
    rule: str | None
    createdAt: str


class QuestionOption(BaseModel):
    id: str
    label: str


class Question(BaseModel):
    questionId: str
    caseId: str
    bankTxnId: str | None
    entity: str
    question: str
    options: list[QuestionOption]
    defaultOption: str | None
    rulePreview: dict | None
    status: Literal["open", "answered"]
    createdAt: str


class DraftAttachment(BaseModel):
    kind: str
    ref: str
    label: str | None = None


class Draft(BaseModel):
    draftId: str
    caseId: str
    kind: Literal["email_customer", "email_supplier"]
    to: str | None
    toName: str | None = None
    partyId: str | None = None
    language: str = "es"
    subject: str
    body: str
    attachments: list[DraftAttachment] = Field(default_factory=list)
    generatedBy: str | None = None
    status: Literal["draft", "sent", "manual"]
    createdAt: str


class CaseRow(Case):
    partyName: str | None


class CasePage(Paged[CaseRow]):
    """Sum of amountEur over every case matching the filter, not only this page."""

    sumAmountEur: int


class CaseDetail(CaseRow):
    question: Question | None
    draft: Draft | None


# ── Stats and run lifecycle ──────────────────────────────────────────────────

class EntityStats(BaseModel):
    entity: str
    name: str
    txns: int
    txnsAuto: int
    reviewQueue: int
    identifiedEur: int


class DayStats(BaseModel):
    date: str
    txns: int
    txnsAuto: int
    reviewQueue: int
    identifiedEur: int


class KindStats(BaseModel):
    kind: str
    cases: int
    amountEur: int


class RuleStats(BaseModel):
    rule: str
    rows: int
    txns: int


class ExceptionStats(BaseModel):
    exception: str
    rows: int
    amountEur: int


class CategoryStats(BaseModel):
    category: str
    txns: int
    amountEur: int


class RunStats(BaseModel):
    runId: str
    phase: str
    entity: str | None
    periodFrom: str | None
    periodTo: str | None
    txns: int
    txnsAuto: int
    identifiedEur: int
    totalEur: int
    reviewQueue: int
    reviewQueueEur: int
    byStatus: dict[str, int]
    byKind: list[KindStats]
    byEntity: list[EntityStats]
    byRule: list[RuleStats]
    byException: list[ExceptionStats]
    byCategory: list[CategoryStats]
    byDay: list[DayStats]
    score: Score | None


class RunStatus(BaseModel):
    runId: str
    status: Literal["queued", "running", "done", "failed"]
    stage: str | None
    stages: dict[str, int]
    startedAt: str
    finishedAt: str | None
    error: str | None


class ValidationIssue(BaseModel):
    row: int | None
    message: str


class ValidationResult(BaseModel):
    ok: bool
    errors: list[ValidationIssue]
    sizeBytes: int
    uncompressedBytes: int
    rows: int
    txns: int


class UploadResult(BaseModel):
    uploadId: str
    phase: str


class CreateRun(BaseModel):
    phase: str
    memoryFrom: str | None = None


class RunCreated(BaseModel):
    runId: str
    status: Literal["queued", "running", "done", "failed"]


# ── Transactions ─────────────────────────────────────────────────────────────

class Assignment(BaseModel):
    itemId: str | None
    documentNumber: str | None
    amountCents: int | None
    currency: str | None
    category: str | None
    exception: str | None


class TxnRow(BaseModel):
    bankTxnId: str
    accountId: str
    entity: str
    bank: str
    statementFormat: str
    bookingDate: str
    amountCents: int
    currency: str
    amountEur: int
    text: str
    counterpartyName: str | None
    rule: str
    confidence: float
    partyId: str | None
    partyName: str | None
    caseId: str | None
    caseStatus: CaseStatus | None
    rowCount: int
    assignments: list[Assignment]


class BankLine(BaseModel):
    bankTxnId: str
    accountId: str
    entity: str
    bank: str
    statementFormat: str
    statementFile: str
    bookingDate: str
    valueDate: str
    amountCents: int
    currency: str
    bankCode: str | None
    bankSubcode: str | None
    ref1: str | None
    ref2: str | None
    text: str
    counterpartyName: str | None
    counterpartyAccount: str | None
    endToEndId: str | None
    remittanceInfo: str | None
    origAmountCents: int | None
    origCurrency: str | None


class ItemSummary(BaseModel):
    itemId: str
    itemType: ItemType
    documentNumber: str
    partyId: str
    partyName: str | None
    issueDate: str
    dueDate: str | None
    currency: str
    totalCents: int
    openAtStartCents: int | None
    openAtEndCents: int | None


class DetailRow(Explanation):
    item: ItemSummary | None


class PartyAlternative(BaseModel):
    partyId: str
    partyName: str | None
    score: float


class PartyResolution(BaseModel):
    partyId: str
    partyName: str | None
    partyKind: Literal["customer", "supplier"]
    payerName: str | None
    how: str
    confidence: float
    alternatives: list[PartyAlternative]


class DocumentFact(BaseModel):
    lineNo: int | None
    documentNumber: str | None
    documentNumberNorm: str | None
    grossCents: int | None
    deductionCents: int | None
    reason: str | None
    paidCents: int | None
    currency: str | None
    customerPo: str | None
    voucher: str | None
    clause: str | None
    clauseValue: dict | None
    method: Literal["parser", "model"]
    model: str | None


class EvidenceDocument(BaseModel):
    type: Literal["document"] = "document"
    path: str
    text: str | None
    facts: list[DocumentFact]


class EvidenceDetailFile(BaseModel):
    type: Literal["detailFile"] = "detailFile"
    path: str
    columns: list[str]
    rows: list[list[str | None]]


class EvidenceRecord(BaseModel):
    type: Literal["record"] = "record"
    fields: dict[str, str | int | float | None]


class EvidenceNone(BaseModel):
    type: Literal["none"] = "none"


class Evidence(SourceRef):
    content: EvidenceDocument | EvidenceDetailFile | EvidenceRecord | EvidenceNone = Field(discriminator="type")


class RelatedTxn(BaseModel):
    bankTxnId: str
    bookingDate: str
    amountCents: int
    currency: str
    text: str
    relation: str


class TxnDetail(BaseModel):
    txn: BankLine
    rows: list[DetailRow]
    party: PartyResolution | None
    candidates: list[Candidate]
    evidence: list[Evidence]
    related: list[RelatedTxn]
    case: Case | None


# ── Decisions, drafts, memory ────────────────────────────────────────────────

class DecisionBody(BaseModel):
    action: Literal["done", "review", "manual"]
    note: str | None = None
    by: str


class AnswerBody(BaseModel):
    optionId: str
    note: str | None = None
    saveAsRule: bool = False
    by: str


class DraftEdit(BaseModel):
    subject: str
    body: str


class DraftAction(BaseModel):
    by: str | None = None


class DraftCreate(BaseModel):
    caseId: str
    kind: Literal["email_customer", "email_supplier"]


class MemoryRuleCreate(BaseModel):
    kind: Literal["payer_is_customer", "reference_alias", "supplier_nets_credit_notes", "always_category",
                  "ignore_suffix", "parent_pays"]
    params: dict
    description: str
    scope: dict = Field(default_factory=dict)
    createdFrom: dict = Field(default_factory=dict)
    by: str


class MemoryRule(BaseModel):
    ruleId: str
    kind: str
    params: dict
    description: str
    scope: dict
    createdFrom: dict
    by: str
    at: str
    active: bool
    affectedTxns: int


# ── Open items, aging, parties ───────────────────────────────────────────────

class ItemHistoryEntry(BaseModel):
    bankTxnId: str
    bookingDate: str
    amountCents: int
    exception: str | None


class OpenItem(BaseModel):
    itemId: str
    itemType: ItemType
    entity: str
    partyId: str
    partyName: str | None
    documentNumber: str
    issueDate: str
    dueDate: str | None
    currency: str
    totalCents: int
    openAtStartCents: int
    appliedCents: int
    openAtEndCents: int
    openAtEndEur: int
    status: Literal["open", "partial", "cleared", "disputed", "returned"]
    daysOverdue: int
    history: list[ItemHistoryEntry]


class AgingParty(BaseModel):
    partyId: str
    partyName: str | None
    entity: str
    openEur: int
    overdueEur: int
    buckets: dict[AgingBucket, int]
    openItems: int
    oldestDaysOverdue: int
    disputes: int
    duplicates: int
    caseId: str | None


class Aging(BaseModel):
    asOf: str | None
    totals: dict[AgingBucket, int]
    openEur: int
    overdueEur: int
    parties: list[AgingParty]


class Party(BaseModel):
    partyId: str
    kind: Literal["customer", "supplier"]
    entity: str
    name: str
    tradeName: str | None
    type: str | None
    country: str | None
    taxId: str | None
    iban: str | None
    paymentTerms: str | None
    currency: str | None
    groupId: str | None
    parentId: str | None
    blockedSince: str | None


class GroupMember(BaseModel):
    partyId: str
    name: str
    entity: str


class PartyDetail(BaseModel):
    party: Party
    group: list[GroupMember]
    items: list[OpenItem]
    transactions: list[TxnRow]
    cases: list[CaseRow]


# ── Package data ─────────────────────────────────────────────────────────────

class FormatPeriod(BaseModel):
    format: str
    from_: str = Field(alias="from")
    to: str | None


class Account(BaseModel):
    accountId: str
    entity: str
    bank: str
    bankName: str | None
    currency: str
    iban: str | None
    purpose: str | None
    inMaster: bool
    formats: list[FormatPeriod]
    txns: int
    inflowCents: int
    outflowCents: int
    netCents: int
    firstDate: str | None
    lastDate: str | None
    reconciledRate: float | None


class DataItem(BaseModel):
    itemId: str
    itemType: ItemType
    entity: str
    documentNumber: str
    partyId: str
    partyName: str | None
    issueDate: str
    dueDate: str | None
    currency: str
    totalCents: int
    openAtStartCents: int | None
    relatedDocument: str | None
    reference: str | None


DocKind = Literal["remittanceAdvice", "invoicePdf", "creditNotePdf", "proformaPdf", "bankAccountNotice"]


class DocumentRow(BaseModel):
    path: str
    kind: DocKind
    entity: str
    format: str
    name: str
    date: str | None
    partyName: str | None


class DocumentDetail(DocumentRow):
    text: str | None
    facts: list[DocumentFact]


class DetailFileRow(BaseModel):
    path: str
    kind: Literal["directDebitBatch", "cardSettlement", "chequeDeposit", "paymentRun"]
    entity: str
    month: str | None
    rows: int
