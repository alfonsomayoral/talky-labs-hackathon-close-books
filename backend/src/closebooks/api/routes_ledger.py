"""Open items, aging by party and the party page."""
from __future__ import annotations

from typing import Annotated, Literal

import orjson
from fastapi import APIRouter, Query, Request

from .errors import not_found
from .query import Paging, Where, fetch, order_by, page_of
from .routes_cases import CASE_ROW
from .routes_txns import TXN_FIELDS, cols
from .schemas import Aging, OpenItem, Paged, PartyDetail

router = APIRouter()

OPEN_ITEM_FIELDS = ["itemId", "itemType", "entity", "partyId", "partyName", "documentNumber", "issueDate", "dueDate",
                    "currency", "totalCents", "openAtStartCents", "appliedCents", "openAtEndCents", "openAtEndEur",
                    "status", "daysOverdue", "history"]
OPEN_ITEM_SORT = {k: f'"{k}"' for k in OPEN_ITEM_FIELDS if k != "history"}
PARTY_FIELDS = ["partyId", "kind", "entity", "name", "tradeName", "type", "country", "taxId", "iban", "paymentTerms",
                "currency", "groupId", "parentId", "blockedSince"]
BUCKETS = {"not_due": '"daysOverdue" = 0', "d1_30": '"daysOverdue" BETWEEN 1 AND 30',
           "d31_60": '"daysOverdue" BETWEEN 31 AND 60', "d61_90": '"daysOverdue" BETWEEN 61 AND 90',
           "d90_plus": '"daysOverdue" > 90'}


def _items(rows: list[dict]) -> list[dict]:
    for r in rows:
        r["history"] = orjson.loads(r["history"]) if r["history"] else []
    return rows


@router.get("/runs/{runId}/open-items", response_model=Paged[OpenItem])
def list_open_items(runId: str, request: Request, paging: Paging, entity: str | None = None,
                    partyId: str | None = None, status: str | None = None, overdue: bool | None = None,
                    q: str | None = None, sort: str | None = None):
    run = request.app.state.store.run(runId)
    w = Where()
    w.isin('"entity"', entity)
    w.isin('"partyId"', partyId)
    w.isin('"status"', status)
    if overdue:
        w.add('"daysOverdue" > 0')
    w.search('"_search"', q)
    page = page_of(run.cursor(), "open_items", ", ".join(f'"{f}"' for f in OPEN_ITEM_FIELDS), w,
                   order_by(sort, OPEN_ITEM_SORT, '"dueDate"', '"itemId"'), paging)
    page["items"] = _items(page["items"])
    return page


@router.get("/runs/{runId}/aging", response_model=Aging)
def aging(runId: str, request: Request, entity: str | None = None,
          partyKind: Annotated[Literal["customer", "supplier"], Query()] = "customer"):
    """Open invoices (ARI for customers, API for suppliers) at the end of the phase, by days past due."""
    run = request.app.state.store.run(runId)
    cur = run.cursor()
    w = Where()
    w.isin('"entity"', entity)
    w.add('"itemType" = ?', "ARI" if partyKind == "customer" else "API")
    w.add('"openAtEndCents" > 0')
    sums = ", ".join(f'coalesce(sum("openAtEndEur") FILTER (WHERE {cond}), 0) AS {name}'
                     for name, cond in BUCKETS.items())
    parties = fetch(cur, f"""
        SELECT i."partyId", any_value(i."partyName") AS "partyName", any_value(i.entity) AS entity,
               sum(i."openAtEndEur") AS "openEur", {sums},
               count(*) AS "openItems", max(i."daysOverdue") AS "oldestDaysOverdue",
               count(*) FILTER (WHERE i.status = 'disputed') AS disputes,
               coalesce(any_value(d.n), 0) AS duplicates, any_value(k."caseId") AS "caseId"
        FROM (SELECT * FROM open_items {w.clause()}) i
        LEFT JOIN (SELECT o."partyId", count(*) AS n FROM rows r JOIN open_items o ON o."itemId" = r."itemId"
                   WHERE r.exception = 'DUPLICATE_PAYMENT' GROUP BY 1) d ON d."partyId" = i."partyId"
        LEFT JOIN (SELECT "partyId", min("caseId") AS "caseId" FROM cases
                   WHERE "bankTxnId" IS NULL AND "partyId" IS NOT NULL GROUP BY 1) k ON k."partyId" = i."partyId"
        GROUP BY i."partyId" """, w.params)
    totals = {b: sum(p[b] for p in parties) for b in BUCKETS}
    for p in parties:
        p["buckets"] = {b: p.pop(b) for b in BUCKETS}
        p["overdueEur"] = p["openEur"] - p["buckets"]["not_due"]
    parties.sort(key=lambda p: (-p["overdueEur"], p["partyId"]))
    return {"asOf": run.as_of, "totals": totals, "openEur": sum(totals.values()),
            "overdueEur": sum(totals.values()) - totals["not_due"], "parties": parties[:200]}


@router.get("/runs/{runId}/parties/{partyId}", response_model=PartyDetail)
def party_detail(runId: str, partyId: str, request: Request):
    run = request.app.state.store.run(runId)
    cur = run.cursor()
    got = fetch(cur, f"SELECT {cols(PARTY_FIELDS)} FROM party WHERE \"partyId\" = ?", [partyId])
    if not got:
        raise not_found("Party", partyId)
    party = got[0]
    group = fetch(cur, 'SELECT "partyId", name, entity FROM party WHERE "partyId" <> ? AND '
                       '(("groupId" IS NOT NULL AND "groupId" = ?) OR "partyId" = ? OR "parentId" = ?) '
                       'ORDER BY "partyId" LIMIT 200',
                  [partyId, party["groupId"], party["parentId"], partyId])
    items = _items(fetch(cur, f'SELECT {cols(OPEN_ITEM_FIELDS)} FROM open_items WHERE "partyId" = ? '
                              f'ORDER BY "dueDate" NULLS LAST, "itemId" LIMIT 200', [partyId]))
    w = Where()
    w.add('"bankTxnId" IN (SELECT "bankTxnId" FROM rows WHERE "partyId" = ?)', partyId)
    txns = fetch(cur, f'SELECT {cols(TXN_FIELDS)} FROM tx {w.clause()} ORDER BY "bookingDate" DESC, "bankTxnId" '
                      f'LIMIT 200', w.params)
    for t in txns:
        t["assignments"] = t["assignments"] or []
    cases = fetch(cur, f'SELECT {cols(CASE_ROW)} FROM cases WHERE "partyId" = ? ORDER BY "priority", "caseId" '
                       f'LIMIT 200', [partyId])
    return {"party": party, "group": group, "items": items, "transactions": txns, "cases": cases}

