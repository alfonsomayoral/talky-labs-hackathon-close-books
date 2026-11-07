"""Bank lines of a run: the list and the detail with its evidence."""
from __future__ import annotations

import csv as csvlib
import re
from typing import Annotated

import duckdb
import orjson
from fastapi import APIRouter, Query, Request

from ..paths import master_path
from .documents import facts_for, read_text
from .errors import not_found
from .query import Paging, Where, fetch, order_by, page_of
from .run_data import RunData, lit, read_csv
from .schemas import Paged, TxnDetail, TxnRow

router = APIRouter()

TXN_FIELDS = ["bankTxnId", "accountId", "entity", "bank", "statementFormat", "bookingDate", "amountCents", "currency",
              "amountEur", "text", "counterpartyName", "rule", "confidence", "partyId", "partyName", "caseId",
              "caseStatus", "rowCount", "assignments"]
SORTABLE = {k: f'"{k}"' for k in TXN_FIELDS if k != "assignments"}
BANK_FIELDS = ["bankTxnId", "accountId", "entity", "bank", "statementFormat", "statementFile", "bookingDate",
               "valueDate", "amountCents", "currency", "bankCode", "bankSubcode", "ref1", "ref2", "text",
               "counterpartyName", "counterpartyAccount", "endToEndId", "remittanceInfo", "origAmountCents",
               "origCurrency"]
CASE_FIELDS = ["caseId", "kind", "status", "priority", "entity", "bankTxnId", "partyId", "itemIds", "amountCents",
               "currency", "amountEur", "bookingDate", "summary", "suggestedAction", "questionId", "draftId", "rule",
               "createdAt"]
ITEM_FIELDS = ["itemId", "itemType", "documentNumber", "partyId", "partyName", "issueDate", "dueDate", "currency",
               "totalCents", "openAtStartCents", "openAtEndCents"]
EXPLANATION_FIELDS = ["bankTxnId", "itemId", "amountCents", "currency", "category", "exception", "rule", "confidence",
                      "partyId", "reference", "sources", "candidates"]


def cols(fields: list[str], prefix: str = "") -> str:
    return ", ".join(f'{prefix}"{f}"' for f in fields)


def txn_rows(cur, where: Where, order: str, paging) -> dict:
    page = page_of(cur, "tx", cols(TXN_FIELDS), where, order, paging)
    for item in page["items"]:
        item["assignments"] = item["assignments"] or []
    return page


@router.get("/runs/{runId}/transactions", response_model=Paged[TxnRow])
def list_transactions(
    runId: str, request: Request, paging: Paging, entity: str | None = None, accountId: str | None = None,
    rule: str | None = None, exception: str | None = None, category: str | None = None,
    caseStatus: str | None = None, statementFormat: str | None = None, q: str | None = None,
    from_: Annotated[str | None, Query(alias="from")] = None, to: str | None = None, sort: str | None = None,
):
    run = request.app.state.store.run(runId)
    w = Where()
    w.isin('"entity"', entity)
    w.isin('"accountId"', accountId)
    w.isin('"rule"', rule)
    w.isin('"caseStatus"', caseStatus)
    w.isin('"statementFormat"', statementFormat)
    for column, raw in (("exception", exception), ("category", category)):
        sub = Where()
        sub.isin(column, raw)
        if sub.parts:
            w.add(f'"bankTxnId" IN (SELECT "bankTxnId" FROM rows {sub.clause()})', *sub.params)
    if from_:
        w.add('"bookingDate" >= ?', from_)
    if to:
        w.add('"bookingDate" <= ?', to)
    w.search('"_search"', q)
    order = order_by(sort, SORTABLE, '"bookingDate"', '"bankTxnId"')
    return txn_rows(run.cursor(), w, order, paging)


# ── detail ───────────────────────────────────────────────────────────────────

def _related(cur, txn_id: str, rows: list[dict]) -> list[dict]:
    items = sorted({r["itemId"] for r in rows if r["itemId"]})
    if not items:
        return []
    mine = {r["itemId"]: r["exception"] for r in rows if r["itemId"]}
    found = fetch(cur, f"""SELECT x."bankTxnId", x."bookingDate", x."amountCents", x.currency, x.text,
                          r."itemId", r.exception FROM rows r JOIN tx x ON x."bankTxnId" = r."bankTxnId"
                          WHERE r."itemId" IN ({",".join("?" * len(items))}) AND r."bankTxnId" <> ?
                          ORDER BY x."bookingDate", x."bankTxnId" LIMIT 100""", [*items, txn_id])
    out, seen = [], set()
    for f in found:
        mine_exc, other_exc = mine[f["itemId"]], f["exception"]
        if mine_exc == "RETURNED" and other_exc != "RETURNED":
            relation = "returnOf"
        elif other_exc == "RETURNED" and mine_exc != "RETURNED":
            relation = "returnedBy"
        elif mine_exc == "DUPLICATE_PAYMENT" and other_exc != "DUPLICATE_PAYMENT":
            relation = "duplicateOf"
        elif other_exc == "DUPLICATE_PAYMENT" and mine_exc != "DUPLICATE_PAYMENT":
            relation = "duplicatedBy"
        else:
            relation = "sameItem"
        if (f["bankTxnId"], relation) not in seen:
            seen.add((f["bankTxnId"], relation))
            out.append({k: f[k] for k in ("bankTxnId", "bookingDate", "amountCents", "currency", "text")}
                       | {"relation": relation})
    return out[:20]


def _party_resolution(run: RunData, cur, txn_id: str, rows: list[dict], bank: dict) -> dict | None:
    """The facts row if the run has one; else the party the rows carry, with the rule as `how`."""
    parquet = run.dir / "facts" / "parties.parquet"
    got = fetch(duckdb.connect(), f'SELECT * FROM read_parquet({lit(parquet)}) WHERE "bankTxnId" = ? LIMIT 1',
                [txn_id]) if parquet.exists() else []
    if not got:
        return _party_from_rows(cur, rows, bank)
    p = got[0]
    names = dict(cur.execute('SELECT "partyId", name FROM party').fetchall())
    alternatives = orjson.loads(p["alternatives"]) if p["alternatives"] else []
    return {"partyId": p["partyId"], "partyName": names.get(p["partyId"]), "partyKind": p["partyKind"],
            "payerName": p["payerName"], "how": p["how"], "confidence": p["confidence"],
            "alternatives": [{"partyId": a["partyId"], "partyName": names.get(a["partyId"]), "score": a["score"]}
                             for a in alternatives]}


ID_COLUMNS = ("batch_id", "settlement_id", "deposit_id", "run_id", "end_to_end_id")
ACCOUNT_COLUMNS = ("account_id", "debtor_account_id")


def _belongs(header: list[str], row: list[str], keys: set[str], account_id: str) -> bool:
    """A row is this movement's when its remittance/settlement/deposit id is one of the movement's AND it is on this
    account (the ids repeat across entities). Files with no such id column fall back to any key in any cell."""
    cell = dict(zip(header, row, strict=False))
    id_columns = [c for c in ID_COLUMNS if c in cell]
    if not id_columns:
        return any(len(c) >= 6 and c in keys for c in row)
    account = next((cell[c] for c in ACCOUNT_COLUMNS if c in cell), None)
    return any(cell[c] in keys for c in id_columns) and (account is None or account == account_id)


def _party_from_rows(cur, rows: list[dict], bank: dict) -> dict | None:
    first = next((r for r in rows if r["partyId"]), None)
    if first is None:
        return None
    found = cur.execute('SELECT name, kind FROM party WHERE "partyId" = ?', [first["partyId"]]).fetchone()
    if found is None:
        return None
    return {"partyId": first["partyId"], "partyName": found[0], "partyKind": found[1],
            "payerName": bank["counterpartyName"], "how": first["rule"], "confidence": first["confidence"],
            "alternatives": []}


def _detail_file(run: RunData, ref: str, bank: dict, references: set[str]) -> dict:
    path = run.phase_file(ref)
    if path is None:
        return {"type": "none"}
    keys = {t for f in ("text", "ref1", "ref2", "endToEndId", "remittanceInfo") for t in (bank[f] or "").split()}
    keys |= references
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csvlib.reader(handle)
        header = next(reader, [])
        rows = [r for r in reader if _belongs(header, r, keys, bank["accountId"])][:500]
    return {"type": "detailFile", "path": ref, "columns": header, "rows": rows}


def _record(fields: dict | None) -> dict:
    return {"type": "none"} if not fields else {"type": "record", "fields": fields}


def _master_row(run: RunData, filename: str, key: str, value: str) -> dict | None:
    got = fetch(duckdb.connect(), f"SELECT * FROM {read_csv(master_path(run.phase_dir, filename))} "
                                  f'WHERE "{key}" = ? LIMIT 1', [value])
    return got[0] if got else None


def _evidence_content(run: RunData, cur, kind: str, ref: str, bank: dict, references: set[str]) -> dict:
    if kind in ("remittanceAdvice", "pdf"):
        found = run.phase_file(ref)
        text, facts = read_text(found.parent, found.name) if found else None, facts_for(run.dir, ref)
        return {"type": "document", "path": ref, "text": text, "facts": facts} if text is not None or facts \
            else {"type": "none"}
    if kind in ("directDebitBatch", "cardSettlement", "chequeDeposit", "paymentRun"):
        return _detail_file(run, ref, bank, references)
    if kind in ("customer", "supplier"):
        got = fetch(cur, 'SELECT * FROM party WHERE "partyId" = ? LIMIT 1', [ref])
        return _record(got[0] if got else None)
    if kind == "bankAccount":
        return _record(_master_row(run, "bank_accounts.csv", "account_id", ref))
    if kind == "fxRate":
        m = re.search(r"([A-Z]{3})\W+(\d{4}-\d{2}-\d{2})", ref)
        got = fetch(cur, "SELECT date::VARCHAR AS date, currency, rate AS unitsPerEur FROM fx WHERE currency = ? "
                         "AND date <= CAST(? AS DATE) ORDER BY date DESC LIMIT 1", list(m.groups())) if m else []
        return _record(got[0] if got else None)
    if kind == "bankLine":
        got = fetch(cur, f"SELECT {cols(BANK_FIELDS)} FROM bank WHERE \"bankTxnId\" = ?", [ref])
        return _record(got[0] if got else None)
    if kind == "memoryRule":
        rule = next((r for r in run.human.read("memory_rules.jsonl") if r["ruleId"] == ref), None)
        return _record(rule and {k: (orjson.dumps(v).decode() if isinstance(v, dict) else v) for k, v in rule.items()})
    if kind == "humanDecision":
        d = next((d for d in run.human.read("decisions.jsonl") if d["decisionId"] == ref), None)
        return _record(d)
    return {"type": "none"}


@router.get("/runs/{runId}/transactions/{bankTxnId}", response_model=TxnDetail)
def transaction_detail(runId: str, bankTxnId: str, request: Request):
    run = request.app.state.store.run(runId)
    cur = run.cursor()
    banks = fetch(cur, f'SELECT {cols(BANK_FIELDS)} FROM bank WHERE "bankTxnId" = ?', [bankTxnId])
    if not banks:
        raise not_found("Transaction", bankTxnId)
    bank = banks[0]
    rows = fetch(cur, f'SELECT {cols(EXPLANATION_FIELDS, "r.")}, o."itemType" AS _t, '
                      f'{", ".join(f'o."{f}" AS "i_{f}"' for f in ITEM_FIELDS if f not in ("itemId", "itemType"))} '
                      f'FROM rows r LEFT JOIN open_items o ON o."itemId" = r."itemId" '
                      f'WHERE r."bankTxnId" = ? ORDER BY r."rowNo"', [bankTxnId])
    detail_rows = []
    for r in rows:
        item = None
        if r["_t"]:
            item = {"itemId": r["itemId"], "itemType": r["_t"]} | {
                f: r[f"i_{f}"] for f in ITEM_FIELDS if f not in ("itemId", "itemType")}
        detail_rows.append({f: r[f] for f in EXPLANATION_FIELDS} | {"item": item})
    candidates = {c["itemId"]: c for r in rows for c in r["candidates"] or []}
    sources = {(s["kind"], s["ref"]): s for r in rows for s in r["sources"] or []}
    references = {r["reference"] for r in rows if r["reference"]}
    evidence = [s | {"content": _evidence_content(run, cur, s["kind"], s["ref"], bank, references)}
                for s in sources.values()]
    case = fetch(cur, f'SELECT {cols(CASE_FIELDS)} FROM cases WHERE "bankTxnId" = ? ORDER BY "caseId" LIMIT 1',
                 [bankTxnId])
    several_parties = len({r["partyId"] for r in rows if r["partyId"]}) > 1  # a remittance paying several parties
    party = None if several_parties else _party_resolution(run, cur, bankTxnId, rows, bank)
    return {"txn": bank, "rows": detail_rows, "party": party,
            "candidates": list(candidates.values()), "evidence": evidence, "related": _related(cur, bankTxnId, rows),
            "case": case[0] if case else None}
