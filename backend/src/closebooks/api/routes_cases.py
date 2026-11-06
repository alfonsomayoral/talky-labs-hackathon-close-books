"""Cases, questions, drafts and memory rules: what a person reads and decides. Writes go to human/ only."""
from __future__ import annotations

from fastapi import APIRouter, Request, Response

from .errors import Problem, not_found
from .human import active_rules, next_id, now_iso, validate_rule
from .query import Paging, Where, fetch, order_by, page_of
from .routes_txns import CASE_FIELDS, cols
from .run_data import RunData
from .schemas import (
    AnswerBody,
    CaseDetail,
    CaseRow,
    DecisionBody,
    Draft,
    DraftAction,
    DraftCreate,
    DraftEdit,
    MemoryRule,
    MemoryRuleCreate,
    Paged,
    Question,
)

router = APIRouter()
CASE_ROW = [*CASE_FIELDS, "partyName"]
CASE_SORT = {k: f'"{k}"' for k in CASE_ROW}
ITEM_PREFIXES = ("ARI-", "ARC-", "API-", "APC-")


def case_detail(run: RunData, case_id: str) -> dict:
    got = fetch(run.cursor(), f'SELECT {cols(CASE_ROW)} FROM cases WHERE "caseId" = ?', [case_id])
    if not got:
        raise not_found("Case", case_id)
    case = got[0]
    question = next((q for q in run.questions() if q["caseId"] == case_id), None)
    draft = next((d for d in run.drafts() if d["caseId"] == case_id), None)
    return {**case, "question": question, "draft": draft}


@router.get("/runs/{runId}/cases", response_model=Paged[CaseRow])
def list_cases(runId: str, request: Request, paging: Paging, status: str | None = None, kind: str | None = None,
               entity: str | None = None, priority: str | None = None, q: str | None = None,
               sort: str | None = None):
    run = request.app.state.store.run(runId)
    w = Where()
    w.isin('"status"', status)
    w.isin('"kind"', kind)
    w.isin('"entity"', entity)
    w.isin('"priority"', priority, int)
    w.search('"_search"', q)
    return page_of(run.cursor(), "cases", cols(CASE_ROW), w,
                   order_by(sort, CASE_SORT, '"priority", "amountEur" DESC', '"caseId"'), paging)


@router.get("/runs/{runId}/cases/{caseId}", response_model=CaseDetail)
def get_case(runId: str, caseId: str, request: Request):
    return case_detail(request.app.state.store.run(runId), caseId)


@router.post("/runs/{runId}/cases/{caseId}/decision", response_model=CaseDetail)
def decide_case(runId: str, caseId: str, body: DecisionBody, request: Request):
    run = request.app.state.store.run(runId)
    case_detail(run, caseId)  # 404 if it does not exist
    run.human.append_with_id("decisions.jsonl", lambda existing: {
        "decisionId": next_id("DEC-", "decisionId", existing, 6), "caseId": caseId, "action": body.action,
        "note": body.note, "by": body.by, "at": now_iso()})
    run.sync_status()
    return case_detail(run, caseId)


# ── questions ────────────────────────────────────────────────────────────────

@router.get("/runs/{runId}/questions", response_model=Paged[Question])
def list_questions(runId: str, request: Request, paging: Paging, status: str | None = None):
    wanted = {s.strip() for s in (status or "").split(",") if s.strip()}
    questions = [q for q in request.app.state.store.run(runId).questions() if not wanted or q["status"] in wanted]
    start = paging.offset
    return {"items": questions[start:start + paging.size], "total": len(questions), "page": paging.page,
            "size": paging.size}


def _party_of_option(run: RunData, option_id: str) -> str:
    """An option is an item (its party) or a party."""
    if option_id.startswith(ITEM_PREFIXES):
        got = run.cursor().execute('SELECT "partyId" FROM open_items WHERE "itemId" = ?', [option_id]).fetchone()
        if got:
            return got[0]
    return option_id


def _create_rule(run: RunData, kind: str, params: dict, description: str, scope: dict, created_from: dict,
                 by: str) -> dict:
    categories = {r[0] for r in run.cursor().execute("SELECT category FROM categories").fetchall()}
    problem = validate_rule(kind, params, categories)
    if problem:
        raise Problem(422, "Invalid memory rule", problem)
    return run.human.append_with_id("memory_rules.jsonl", lambda existing: {
        "ruleId": next_id("MR-", "ruleId", existing, 4), "kind": kind, "params": params, "description": description,
        "scope": scope, "createdFrom": created_from, "by": by, "at": now_iso(), "active": True})


@router.post("/runs/{runId}/questions/{questionId}/answer", response_model=CaseDetail)
def answer_question(runId: str, questionId: str, body: AnswerBody, request: Request):
    run = request.app.state.store.run(runId)
    question = next((q for q in run.questions() if q["questionId"] == questionId), None)
    if question is None:
        raise not_found("Question", questionId)
    if question["status"] == "answered":
        raise Problem(409, "Question already answered", questionId)
    if body.optionId not in {o["id"] for o in question["options"]}:
        raise Problem(422, "Invalid request", f"{body.optionId!r} is not an option of {questionId}")
    if body.saveAsRule and body.optionId != "none":
        preview = question.get("rulePreview")
        if not preview:
            raise Problem(422, "Invalid request", "The question has no rule preview to save")
        party = _party_of_option(run, body.optionId)
        params = {k: (party if k in ("partyId", "forPartyId") or str(v).startswith("<") else v)
                  for k, v in preview.items() if k not in ("kind", "description")}
        _create_rule(run, preview["kind"], params, preview.get("description", ""), {"entity": question["entity"]},
                     {"questionId": questionId, "caseId": question["caseId"]}, body.by)
    run.human.append_with_id("decisions.jsonl", lambda existing: {
        "decisionId": next_id("DEC-", "decisionId", existing, 6), "questionId": questionId,
        "caseId": question["caseId"], "optionId": body.optionId, "note": body.note, "saveAsRule": body.saveAsRule,
        "by": body.by, "at": now_iso()})
    run.sync_status()
    return case_detail(run, question["caseId"])


# ── drafts ───────────────────────────────────────────────────────────────────

def _draft(run: RunData, draft_id: str) -> dict:
    got = next((d for d in run.drafts() if d["draftId"] == draft_id), None)
    if got is None:
        raise not_found("Draft", draft_id)
    return got


@router.get("/runs/{runId}/drafts", response_model=Paged[Draft])
def list_drafts(runId: str, request: Request, paging: Paging, status: str | None = None):
    wanted = {s.strip() for s in (status or "").split(",") if s.strip()}
    drafts = [d for d in request.app.state.store.run(runId).drafts() if not wanted or d["status"] in wanted]
    return {"items": drafts[paging.offset:paging.offset + paging.size], "total": len(drafts), "page": paging.page,
            "size": paging.size}


def _write_outbox(run: RunData, draft_id: str, status: str, by: str | None, edit: DraftEdit | None = None) -> dict:
    draft = _draft(run, draft_id)
    if draft["status"] != "draft":
        raise Problem(409, "Draft already closed", f"{draft_id} is {draft['status']}")
    run.human.append("outbox.jsonl", {
        "draftId": draft_id, "status": status, "subject": edit.subject if edit else draft["subject"],
        "body": edit.body if edit else draft["body"], "to": draft["to"], "attachments": draft.get("attachments", []),
        "by": by, "at": now_iso()})
    return _draft(run, draft_id)


@router.put("/runs/{runId}/drafts/{draftId}", response_model=Draft)
def edit_draft(runId: str, draftId: str, body: DraftEdit, request: Request):
    return _write_outbox(request.app.state.store.run(runId), draftId, "draft", None, body)


@router.post("/runs/{runId}/drafts/{draftId}/send", response_model=Draft)
def send_draft(runId: str, draftId: str, request: Request, body: DraftAction | None = None):
    """A record in outbox.jsonl: no e-mail leaves."""
    return _write_outbox(request.app.state.store.run(runId), draftId, "sent", body.by if body else None)


@router.post("/runs/{runId}/drafts/{draftId}/manual", response_model=Draft)
def manual_draft(runId: str, draftId: str, request: Request, body: DraftAction | None = None):
    return _write_outbox(request.app.state.store.run(runId), draftId, "manual", body.by if body else None)


@router.post("/runs/{runId}/drafts", response_model=Draft)
def create_draft(runId: str, body: DraftCreate, request: Request):
    request.app.state.store.run(runId)
    raise Problem(501, "Not implemented", "Draft generation with a model is not available yet")


# ── memory rules ─────────────────────────────────────────────────────────────

def _with_affected(run: RunData, rules: list[dict]) -> list[dict]:
    counts = dict(run.cursor().execute("""SELECT s.ref, count(DISTINCT "bankTxnId") FROM (
        SELECT "bankTxnId", unnest(sources) AS s FROM rows WHERE rule = 'MEMORY-RULE') WHERE s.kind = 'memoryRule'
        GROUP BY 1""").fetchall())
    return [{**r, "affectedTxns": counts.get(r["ruleId"], 0)} for r in rules]


@router.get("/runs/{runId}/memory-rules", response_model=list[MemoryRule])
def list_memory_rules(runId: str, request: Request):
    run = request.app.state.store.run(runId)
    return _with_affected(run, active_rules(run.human.read("memory_rules.jsonl")))


@router.post("/runs/{runId}/memory-rules", response_model=MemoryRule, status_code=201)
def create_memory_rule(runId: str, body: MemoryRuleCreate, request: Request):
    run = request.app.state.store.run(runId)
    rule = _create_rule(run, body.kind, body.params, body.description, body.scope, body.createdFrom, body.by)
    return _with_affected(run, [rule])[0]


@router.delete("/runs/{runId}/memory-rules/{ruleId}", status_code=204)
def delete_memory_rule(runId: str, ruleId: str, request: Request):
    """Appends the rule again with active=false: the file keeps its history and the last line wins."""
    run = request.app.state.store.run(runId)
    rule = next((r for r in active_rules(run.human.read("memory_rules.jsonl")) if r["ruleId"] == ruleId), None)
    if rule is None:
        raise not_found("Memory rule", ruleId)
    run.human.append("memory_rules.jsonl", {**rule, "active": False, "deletedAt": now_iso()})
    return Response(status_code=204)
