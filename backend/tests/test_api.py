"""CONTRACT §5 over a synthetic run: filters, sort, paging, magnitudes, human/ writes and path safety."""
from __future__ import annotations

import io
import json
import sys
import threading
import time
import zipfile

import pytest
from api_fixture import ADVICE, build_phase, build_run
from fastapi.testclient import TestClient

from closebooks import paths
from closebooks.api.app import create_app
from closebooks.api.routes_txns import _belongs
from closebooks.api.run_data import RunData
from closebooks.api.store import Store

RUN = "p-20261107-021000"


@pytest.fixture
def env(tmp_path, monkeypatch):
    db, runs = tmp_path / "db", tmp_path / "runs"
    db.mkdir()
    runs.mkdir()
    monkeypatch.setattr(paths, "DB", db)
    monkeypatch.setattr(paths, "PKG", tmp_path / "pkg")
    monkeypatch.setattr(paths, "RUNS", runs)
    build_phase(db)
    build_run(runs, RUN, score={"score": 61.5, "metrics": {"x": 1}, "segments": {}, "ok": True, "errors": []})
    build_run(runs, "p-20250101-000000", created="2025-01-01T00:00:00+01:00")
    fake = lambda phase, out: [sys.executable, "-c", (  # noqa: E731
        "import json,pathlib,sys;o=pathlib.Path(sys.argv[1]);o.mkdir(parents=True,exist_ok=True);"
        "(o/'run.json').write_text(json.dumps({'runId':o.name,'phase':sys.argv[2],'createdAt':'2026-11-07T03:00:00+01:00',"
        "'stages':{'load':1}}))"), str(out), phase]
    return TestClient(create_app(store=Store(runs, command=fake))), runs, tmp_path


@pytest.fixture
def api(env):
    return env[0]


def ids(page):
    return [i["bankTxnId"] for i in page["items"]]


def get(api, url, **params):
    r = api.get(f"/api/runs/{RUN}{url}", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_runs_newest_first_with_summary(api):
    runs = api.get("/api/runs").json()
    assert [r["runId"] for r in runs] == [RUN, "p-20250101-000000"]
    assert runs[0]["score"] == 61.5 and runs[0]["modelCalls"] == 3 and runs[0]["modelCostUsd"] == 0.25
    assert runs[1]["score"] is None
    full = api.get(f"/api/runs/{RUN}").json()
    assert set(full["score"]) == {"score", "metrics", "segments"}


def test_filters_accept_several_values(api):
    assert len(get(api, "/transactions", entity="E1,E2")["items"]) == 9
    assert ids(get(api, "/transactions", entity="E2", sort="bankTxnId")) == ["BT-5", "BT-7"]
    assert ids(get(api, "/transactions", rule="REF-EXACT,ADVICE-TXT", sort="bankTxnId")) == ["BT-1", "BT-6", "BT-8"]
    assert ids(get(api, "/transactions", caseStatus="fallback,question", sort="bankTxnId")) == ["BT-3", "BT-4", "BT-7"]
    assert ids(get(api, "/transactions", exception="RETURNED,UNIDENTIFIED", sort="bankTxnId")) == ["BT-4", "BT-6"]
    assert ids(get(api, "/transactions", category="BANK_FEES", sort="bankTxnId")) == ["BT-3", "BT-7"]
    camt = get(api, "/transactions", statementFormat="camt053", sort="bankTxnId")
    assert ids(camt) == ["BT-5", "BT-7", "BT-8", "BT-9"]
    assert ids(get(api, "/transactions", accountId="E2-BK-USD", sort="bankTxnId")) == ["BT-5", "BT-7"]
    window = get(api, "/transactions", **{"from": "2025-07-10", "to": "2025-07-11"}, sort="bankTxnId")
    assert ids(window) == ["BT-6", "BT-7"]


def test_search_ignores_case_and_accents_and_finds_document_numbers(api):
    assert ids(get(api, "/transactions", q="NANDU", sort="bankTxnId")) == ["BT-1", "BT-6", "BT-8"]
    assert ids(get(api, "/transactions", q="fv3", sort="bankTxnId")) == ["BT-2", "BT-9"]
    assert [c["caseId"] for c in get(api, "/cases", q="MARIA rubio")["items"]] == ["CASE-BT-4"]
    assert [c["caseId"] for c in get(api, "/cases", q="acme nandu")["items"]] == [
        "CASE-overdue-1", "CASE-BT-2"]  # by partyName


def test_multi_criteria_sort(api):
    # priority ascending, then amountEur descending
    cases = get(api, "/cases", sort="priority,-amountEur")["items"]
    assert [c["caseId"] for c in cases] == ["CASE-BT-4", "CASE-overdue-1", "CASE-BT-2", "CASE-BT-3", "CASE-BT-7"]
    cases = get(api, "/cases", sort="-priority,amountEur")["items"]
    assert [c["caseId"] for c in cases][:2] == ["CASE-BT-7", "CASE-BT-3"]
    assert ids(get(api, "/transactions", sort="entity,-amountCents"))[:3] == ["BT-1", "BT-2", "BT-4"]


def test_unknown_sort_field_is_a_problem(api):
    r = api.get(f"/api/runs/{RUN}/transactions", params={"sort": "nope"})
    assert r.status_code == 422 and r.headers["content-type"].startswith("application/problem+json")


def test_pagination_and_its_limit(api):
    page = get(api, "/transactions", size=4, page=3, sort="bankTxnId")
    assert (page["total"], page["page"], page["size"], ids(page)) == (9, 3, 4, ["BT-9"])
    assert get(api, "/transactions", size=200)["size"] == 200
    for bad in ({"size": 201}, {"size": 0}, {"page": 0}):
        r = api.get(f"/api/runs/{RUN}/transactions", params=bad)
        assert r.status_code == 422 and r.headers["content-type"].startswith("application/problem+json")


def test_txn_row_amounts_assignments_and_party(api):
    rows = {t["bankTxnId"]: t for t in get(api, "/transactions")["items"]}
    usd = rows["BT-5"]
    assert (usd["amountCents"], usd["amountEur"]) == (10000, 8000)  # 100.00 USD at 1.25 (2025-06-30 rate)
    assert rows["BT-3"]["amountCents"] == -7500
    assert rows["BT-7"]["amountEur"] == -4545  # 50.00 USD at 1.10 (2025-07-10 rate)
    split = rows["BT-2"]
    assert split["rowCount"] == 2 and [a["documentNumber"] for a in split["assignments"]] == ["FV2", "FV3"]
    assert split["partyName"] == "Acme Ñandú S.L." and split["caseStatus"] == "needs_review"
    assert rows["BT-1"]["caseId"] is None


def test_detail_has_rows_evidence_related_and_case(api):
    d = get(api, "/transactions/BT-8")
    assert d["txn"]["amountCents"] == 8000 and d["txn"]["counterpartyName"] == "Acme Ñandú S.L."
    assert d["rows"][0]["item"]["documentNumber"] == "FV5" and d["rows"][0]["item"]["openAtEndCents"] == 0
    by_kind = {e["kind"]: e["content"] for e in d["evidence"]}
    assert by_kind["remittanceAdvice"]["type"] == "document"
    assert "Aviso de pago 8826032134" in by_kind["remittanceAdvice"]["text"]
    assert by_kind["remittanceAdvice"]["facts"][0]["documentNumber"] == "FV25-1"
    assert by_kind["customer"]["type"] == "record" and by_kind["customer"]["fields"]["name"] == "Acme Ñandú S.L."

    returned = get(api, "/transactions/BT-6")
    assert [(r["bankTxnId"], r["relation"]) for r in returned["related"]] == [("BT-1", "returnOf")]
    original = get(api, "/transactions/BT-1")
    assert [(r["bankTxnId"], r["relation"]) for r in original["related"]] == [("BT-6", "returnedBy")]
    assert original["party"]["partyName"] == "Acme Ñandú S.L."
    assert original["party"]["alternatives"][0]["partyId"] == "C2"

    split = get(api, "/transactions/BT-2")
    assert [c["itemId"] for c in split["candidates"]] == ["ARI-3"] and split["case"]["caseId"] == "CASE-BT-2"


def test_detail_file_evidence_only_has_this_movements_rows(api):
    content = get(api, "/transactions/BT-5")["evidence"][0]["content"]
    assert content["type"] == "detailFile" and content["columns"][0] == "batch_id"
    # not B99 (other batch) and not E1's line of the same batch id (other account)
    assert content["rows"] == [["B77", "E2-BK-USD", "B77-0001", "VTM-1", "100.00"]]


def test_party_is_null_when_the_rows_pay_several_parties(api):
    assert get(api, "/transactions/BT-1")["party"]["partyId"] == "C1"  # one party: resolution shown
    split = get(api, "/transactions/BT-9")
    assert {r["partyId"] for r in split["rows"]} == {"C1", "C2"} and split["party"] is None


def test_evidence_path_traversal_leaks_nothing(api):
    evidence = {e["ref"]: e["content"] for e in get(api, "/transactions/BT-8")["evidence"]}
    assert evidence["../../secret.txt"] == {"type": "none"}


def test_unknown_ids_are_404_problems(api):
    for url in (f"/api/runs/{RUN}/transactions/BT-404", f"/api/runs/{RUN}/cases/CASE-404", "/api/runs/nope",
                f"/api/runs/{RUN}/parties/X", "/api/no-such-route", "/api/data/missing/accounts"):
        r = api.get(url)
        assert r.status_code == 404 and r.headers["content-type"].startswith("application/problem+json"), url
        assert r.json()["status"] == 404


def test_stats_are_positive_magnitudes_and_match_definitions(api):
    s = get(api, "/stats")
    assert s["txns"] == 9 and s["periodFrom"] == "2025-07-01" and s["periodTo"] == "2025-07-12"
    # queue: BT-2, BT-3, BT-4, BT-7 and the overdue case. BT-3 is stored negative and must be reported positive.
    assert s["reviewQueue"] == 5 and s["reviewQueueEur"] == 50000 + 7500 + 30000 + 4000 + 121000
    assert s["byStatus"] == {"needs_review": 2, "fallback": 2, "question": 1}
    assert {k["kind"]: (k["cases"], k["amountEur"]) for k in s["byKind"]}["unknown_debit"] == (2, 11500)
    # automatic = no case in the queue: BT-1, BT-5, BT-6, BT-8, BT-9
    assert s["txnsAuto"] == 5
    # identified = txns with an item row: BT-1, BT-2, BT-5, BT-6, BT-8, BT-9
    assert s["identifiedEur"] == 121000 + 50000 + 8000 + 121000 + 8000 + 6000
    assert all(v >= 0 for v in (s["totalEur"], s["identifiedEur"], s["reviewQueueEur"]))
    assert {e["entity"]: e["reviewQueue"] for e in s["byEntity"]} == {"E1": 4, "E2": 1}
    assert {e["entity"]: e["name"] for e in s["byEntity"]}["E2"] == "Dos Inc."
    assert {r["rule"]: (r["rows"], r["txns"]) for r in s["byRule"]}["PARTY-AMOUNT"] == (2, 1)
    assert {e["exception"]: e["rows"] for e in s["byException"]} == {"PARTIAL": 1, "RETURNED": 1, "UNIDENTIFIED": 1}
    assert {e["exception"]: e["amountEur"] for e in s["byException"]}["UNIDENTIFIED"] == 30000
    assert {c["category"]: (c["txns"], c["amountEur"]) for c in s["byCategory"]}["BANK_FEES"] == (2, 7500 + 4545)
    day = {d["date"]: d for d in s["byDay"]}["2025-07-03"]
    assert (day["txns"], day["txnsAuto"], day["reviewQueue"]) == (1, 0, 1)
    assert s["score"]["score"] == 61.5


def test_stats_by_entity_and_empty_entity(api):
    e2 = get(api, "/stats", entity="E2")
    assert (e2["txns"], e2["reviewQueue"], e2["reviewQueueEur"], e2["entity"]) == (2, 1, 4000, "E2")
    assert get(api, "/stats", entity="NOPE")["txns"] == 0


def test_decision_writes_human_file_and_moves_the_queue(api, env):
    runs = env[1]
    r = api.post(f"/api/runs/{RUN}/cases/CASE-BT-3/decision", json={"action": "done", "note": "ok", "by": "ana"})
    assert r.status_code == 200 and r.json()["status"] == "done"
    lines = [json.loads(line) for line in (runs / RUN / "human" / "decisions.jsonl").read_text().splitlines()]
    assert len(lines) == 1 and lines[0]["caseId"] == "CASE-BT-3" and lines[0]["by"] == "ana"
    assert get(api, "/stats")["reviewQueue"] == 4
    assert get(api, "/transactions/BT-3")["case"]["status"] == "done"
    assert ids(get(api, "/transactions", caseStatus="done")) == ["BT-3"]
    api.post(f"/api/runs/{RUN}/cases/CASE-BT-3/decision", json={"action": "review", "by": "ana"})
    assert get(api, "/cases/CASE-BT-3")["status"] == "needs_review"  # the latest decision wins
    assert api.post(f"/api/runs/{RUN}/cases/CASE-404/decision", json={"action": "done", "by": "a"}).status_code == 404
    assert api.post(f"/api/runs/{RUN}/cases/CASE-BT-3/decision", json={"action": "nuke", "by": "a"}).status_code == 422
    assert not [p for p in (runs / RUN).iterdir() if p.name == "decisions.jsonl"]  # nothing outside human/


def test_concurrent_decisions_all_land_with_unique_ids(api, env):
    errors = []

    def decide(n):
        r = api.post(f"/api/runs/{RUN}/cases/CASE-BT-{2 + n % 2}/decision", json={"action": "done", "by": f"u{n}"})
        if r.status_code != 200:
            errors.append(r.text)

    threads = [threading.Thread(target=decide, args=(n,)) for n in range(24)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    lines = (env[1] / RUN / "human" / "decisions.jsonl").read_text().splitlines()
    parsed = [json.loads(line) for line in lines]
    assert not errors and len(parsed) == 24 and len({d["decisionId"] for d in parsed}) == 24


def test_answer_saves_a_rule_with_the_party_of_the_chosen_item(api, env):
    r = api.post(f"/api/runs/{RUN}/questions/Q-1/answer",
                 json={"optionId": "ARI-3", "note": "lo sé", "saveAsRule": True, "by": "ana"})
    assert r.status_code == 200 and r.json()["status"] == "done" and r.json()["question"]["status"] == "answered"
    rules = [json.loads(line) for line in (env[1] / RUN / "human" / "memory_rules.jsonl").read_text().splitlines()]
    assert rules[0]["ruleId"] == "MR-0001" and rules[0]["kind"] == "payer_is_customer"
    assert rules[0]["params"] == {"payerName": "MARIA RUBIO", "partyId": "C2"}
    assert rules[0]["createdFrom"] == {"questionId": "Q-1", "caseId": "CASE-BT-4"}
    assert api.post(f"/api/runs/{RUN}/questions/Q-1/answer", json={"optionId": "none", "by": "a"}).status_code == 409
    assert [q["status"] for q in get(api, "/questions")["items"]] == ["answered"]
    assert get(api, "/questions", status="open")["items"] == []


def test_answer_rejects_options_that_do_not_exist_and_writes_nothing(api, env):
    r = api.post(f"/api/runs/{RUN}/questions/Q-1/answer", json={"optionId": "ARI-X", "saveAsRule": True, "by": "a"})
    assert r.status_code == 422 and not (env[1] / RUN / "human" / "decisions.jsonl").exists()
    api.post(f"/api/runs/{RUN}/questions/Q-1/answer", json={"optionId": "none", "saveAsRule": True, "by": "a"})
    assert not (env[1] / RUN / "human" / "memory_rules.jsonl").exists()  # "none" saves no rule


def test_memory_rules_validate_count_affected_and_delete(api, env):
    bad = api.post(f"/api/runs/{RUN}/memory-rules", json={
        "kind": "always_category", "params": {"category": "NOPE", "textPattern": "x"}, "description": "d", "by": "a"})
    assert bad.status_code == 422 and "NOPE" in bad.json()["detail"]
    assert api.post(f"/api/runs/{RUN}/memory-rules", json={
        "kind": "ignore_suffix", "params": {"partyId": "C1", "regex": "("}, "description": "d", "by": "a"}
    ).status_code == 422
    ok = api.post(f"/api/runs/{RUN}/memory-rules", json={
        "kind": "always_category", "params": {"category": "BANK_FEES", "textPattern": "COMISION"},
        "description": "Comisiones", "scope": {"entity": "E1"}, "by": "ana"})
    assert ok.status_code == 201 and ok.json()["ruleId"] == "MR-0001" and ok.json()["affectedTxns"] == 1  # BT-9
    listed = get(api, "/memory-rules")
    assert [(r["ruleId"], r["affectedTxns"], r["active"]) for r in listed] == [("MR-0001", 1, True)]
    assert api.delete(f"/api/runs/{RUN}/memory-rules/MR-0001").status_code == 204
    assert get(api, "/memory-rules") == []
    assert len((env[1] / RUN / "human" / "memory_rules.jsonl").read_text().splitlines()) == 2
    assert api.delete(f"/api/runs/{RUN}/memory-rules/MR-0001").status_code == 404


def test_drafts_edit_send_manual_and_generation_not_implemented(api, env):
    edited = api.put(f"/api/runs/{RUN}/drafts/D-1", json={"subject": "Nuevo asunto", "body": "Nuevo cuerpo"})
    assert edited.status_code == 200 and edited.json()["subject"] == "Nuevo asunto"
    sent = api.post(f"/api/runs/{RUN}/drafts/D-1/send", json={"by": "ana"}).json()
    assert sent["status"] == "sent" and sent["body"] == "Nuevo cuerpo"
    assert api.post(f"/api/runs/{RUN}/drafts/D-1/send").status_code == 409
    assert api.put(f"/api/runs/{RUN}/drafts/D-1", json={"subject": "x", "body": "y"}).status_code == 409
    assert api.post(f"/api/runs/{RUN}/drafts/D-2/manual").json()["status"] == "manual"
    assert {d["draftId"]: d["status"] for d in get(api, "/drafts")["items"]} == {"D-1": "sent", "D-2": "manual"}
    assert get(api, "/drafts", status="draft")["total"] == 0
    outbox = [json.loads(line) for line in (env[1] / RUN / "human" / "outbox.jsonl").read_text().splitlines()]
    assert [o["status"] for o in outbox] == ["draft", "sent", "manual"]
    assert get(api, "/cases/CASE-overdue-1")["draft"]["draftId"] == "D-1"
    r = api.post(f"/api/runs/{RUN}/drafts", json={"caseId": "CASE-overdue-1", "kind": "email_customer"})
    assert r.status_code == 501 and r.headers["content-type"].startswith("application/problem+json")
    assert (env[1] / RUN / "drafts.jsonl").read_text().count("D-") == 2  # the backend's file is never rewritten


def test_open_items_filters_and_aging_buckets(api):
    assert [i["itemId"] for i in get(api, "/open-items", overdue="true", sort="itemId")["items"]] == [
        "API-1", "ARI-1", "ARI-3"]
    page = get(api, "/open-items", status="partial,open", entity="E1", sort="-openAtEndCents,itemId")
    assert [i["itemId"] for i in page["items"]] == ["ARI-2", "ARI-3", "API-1"]
    item = {i["itemId"]: i for i in get(api, "/open-items")["items"]}["ARI-1"]
    assert (item["daysOverdue"], item["partyName"], item["openAtEndEur"]) == (41, "Acme Ñandú S.L.", 121000)
    aging = get(api, "/aging")
    assert aging["asOf"] == "2025-07-12"
    assert aging["totals"] == {"not_due": 30000, "d1_30": 0, "d31_60": 121000, "d61_90": 20000, "d90_plus": 0}
    assert (aging["openEur"], aging["overdueEur"]) == (171000, 141000)
    first = aging["parties"][0]
    assert first["partyId"] == "C1" and first["overdueEur"] == 121000 and first["caseId"] == "CASE-overdue-1"
    assert first["buckets"]["not_due"] == 30000 and first["openItems"] == 2 and first["oldestDaysOverdue"] == 41
    suppliers = get(api, "/aging", partyKind="supplier")
    assert suppliers["totals"]["d1_30"] == 5000 and suppliers["parties"][0]["partyId"] == "S1"
    assert get(api, "/aging", entity="E2")["parties"] == []


def test_party_detail(api):
    d = get(api, "/parties/C1")
    assert d["party"]["name"] == "Acme Ñandú S.L." and d["party"]["kind"] == "customer"
    assert [g["partyId"] for g in d["group"]] == ["C2"]
    assert [i["itemId"] for i in d["items"]][0] == "ARI-1"
    assert {t["bankTxnId"] for t in d["transactions"]} == {"BT-1", "BT-2", "BT-6", "BT-8", "BT-9"}
    assert {c["caseId"] for c in d["cases"]} == {"CASE-BT-2", "CASE-overdue-1"}


# ── package data ─────────────────────────────────────────────────────────────

def test_accounts_formats_totals_and_reconciled_rate(api):
    accounts = {a["accountId"]: a for a in api.get("/api/data/p/accounts", params={"runId": RUN}).json()}
    e1 = accounts["E1-BK-EUR"]
    assert e1["formats"] == [{"format": "n43", "from": "2025-07-01", "to": "2025-07-12"},
                             {"format": "camt053", "from": "2025-07-12", "to": None}]
    assert (e1["txns"], e1["inflowCents"], e1["outflowCents"], e1["netCents"]) == (7, 215000, 128500, 86500)
    assert e1["inMaster"] and e1["bankName"] == "Banco K" and e1["reconciledRate"] == pytest.approx(4 / 7)
    assert accounts["E2-BK-USD"]["inMaster"] is False
    assert accounts["E1-BK-IDLE"]["txns"] == 0 and accounts["E1-BK-IDLE"]["reconciledRate"] is None
    assert api.get("/api/data/p/accounts").json()[0]["reconciledRate"] is None


def test_package_items_parties_documents_detail_files(api):
    data = lambda path, **p: api.get(f"/api/data/p/{path}", params=p).json()  # noqa: E731
    items = data("items", type="ARI,ARC", entity="E1", sort="itemId")
    assert [i["itemId"] for i in items["items"]] == ["ARC-1", "ARI-1", "ARI-OLD"] and items["total"] == 3
    by_id = {i["itemId"]: i for i in items["items"]}
    assert by_id["ARI-1"]["openAtStartCents"] == 121000 and by_id["ARI-1"]["reference"] == "PO-7"
    assert by_id["ARC-1"]["relatedDocument"] == "FV1" and by_id["ARI-OLD"]["partyName"] == "Beta, S.A."
    assert [i["itemId"] for i in data("items", q="acme", type="ARI")["items"]] == ["ARI-1"]
    assert [p["partyId"] for p in data("parties", kind="supplier")["items"]] == ["S1"]
    assert [p["partyId"] for p in data("parties", q="NANDU")["items"]] == ["C1"]
    docs = data("documents", kind="remittanceAdvice")
    assert [d["path"] for d in docs["items"]] == [ADVICE] and docs["items"][0]["date"] == "2025-07-12"
    detail = data(f"documents/{ADVICE}", runId=RUN)
    assert "Aviso de pago" in detail["text"] and detail["facts"][0]["documentNumber"] == "FV25-1"
    files = data("detail-files", kind="directDebitBatch")["items"]
    assert files == [{"path": "direct_debit_batches/E2_B77_202507.csv", "kind": "directDebitBatch", "entity": "E2",
                      "month": "2025-07", "rows": 3}]


def test_document_path_traversal_is_refused(api):
    for path in ("..%2F..%2Fsecret.txt", "%2e%2e%2f%2e%2e%2fsecret.txt", "remittance_advices%2F..%2F..%2Fsecret.txt",
                 "%2Fetc%2Fpasswd"):
        r = api.get(f"/api/data/p/documents/{path}")
        assert r.status_code in (400, 404) and "TOP SECRET" not in r.text, path
        assert r.headers["content-type"].startswith("application/problem+json")


# ── uploads and runs ─────────────────────────────────────────────────────────

def _zip(members: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return buffer.getvalue()


def test_upload_rejects_zip_slip_and_cleans_up(api, env):
    db = env[2] / "db"
    before = set(db.iterdir())
    evil = _zip({"bank_transactions.csv.gz": b"x", "../escaped.txt": "pwned"})
    r = api.post("/api/uploads", files={"file": ("evil.zip", evil)})
    assert r.status_code == 400 and r.headers["content-type"].startswith("application/problem+json")
    assert not (db.parent / "escaped.txt").exists() and not (db / "escaped.txt").exists()
    assert set(db.iterdir()) == before
    absolute = _zip({"/tmp/absolute-escape.txt": "pwned"})
    assert api.post("/api/uploads", files={"file": ("abs.zip", absolute)}).status_code == 400
    assert api.post("/api/uploads", files={"file": ("junk.zip", b"not a zip")}).status_code == 400
    assert api.post("/api/uploads", files={"file": ("p.zip", _zip({"readme.txt": "hi"}))}).status_code == 422
    assert set(db.iterdir()) == before


def test_upload_unpacks_a_phase_and_it_can_be_run(api, env):
    db, runs = env[2] / "db", env[1]
    r = api.post("/api/uploads", files={"file": ("Mi Fase.zip", _zip({"fase/bank_transactions.csv.gz": b"x",
                                                                     "fase/masters/entities.csv": "entity\n"}))})
    assert r.status_code == 201 and r.json() == {"uploadId": "Mi-Fase", "phase": "Mi-Fase"}
    assert (db / "Mi-Fase" / "bank_transactions.csv.gz").read_bytes() == b"x"
    assert (db / "Mi-Fase" / "masters" / "entities.csv").exists()
    again = api.post("/api/uploads", files={"file": ("Mi Fase.zip", _zip({"bank_transactions.csv.gz": b"y"}))})
    assert again.json()["uploadId"] == "Mi-Fase-2"

    created = api.post("/api/runs", json={"phase": "Mi-Fase"})
    assert created.status_code == 202
    run_id = created.json()["runId"]
    for _ in range(100):
        status = api.get(f"/api/runs/{run_id}/status").json()
        if status["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert status["status"] == "done" and status["stages"] == {"load": 1} and status["error"] is None
    assert (runs / run_id / "run.json").exists()
    assert api.post("/api/runs", json={"phase": "ghost"}).status_code == 404
    assert api.get("/api/runs/ghost/status").status_code == 404


def test_failed_run_reports_its_error(env):
    _, runs, tmp = env
    boom = lambda phase, out: [sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"]  # noqa: E731
    client = TestClient(create_app(store=Store(runs, command=boom)))
    run_id = client.post("/api/runs", json={"phase": "p", "memoryFrom": RUN}).json()["runId"]
    for _ in range(100):
        status = client.get(f"/api/runs/{run_id}/status").json()
        if status["status"] == "failed":
            break
        time.sleep(0.05)
    assert status["status"] == "failed" and "boom" in status["error"] and status["finishedAt"]


def test_memory_from_copies_the_rules_into_the_new_run(env):
    _, runs, _ = env
    client = TestClient(create_app(store=Store(runs, command=lambda p, o: [sys.executable, "-c", "pass"])))
    client.post(f"/api/runs/{RUN}/memory-rules", json={
        "kind": "supplier_nets_credit_notes", "params": {"partyId": "S1"}, "description": "d", "by": "a"})
    run_id = client.post("/api/runs", json={"phase": "p", "memoryFrom": RUN}).json()["runId"]
    assert json.loads((runs / run_id / "human" / "memory_rules.jsonl").read_text())["params"] == {"partyId": "S1"}
    assert client.post("/api/runs", json={"phase": "p", "memoryFrom": "ghost"}).status_code == 404


def test_cors_is_open_to_localhost_only(api):
    ok = api.get("/api/runs", headers={"Origin": "http://localhost:5173"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    other = api.get("/api/runs", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_openapi_json_is_up_to_date(tmp_path):
    from pathlib import Path

    committed = json.loads((Path(__file__).parents[1] / "openapi.json").read_text())
    assert create_app(store=Store(tmp_path)).openapi() == committed, "regenerate backend/openapi.json (see README)"


def test_payment_evidence_cited_by_transfer_shows_only_that_transfer_on_that_account():
    header = ["run_id", "debtor_account_id", "end_to_end_id", "document_number"]
    keys = {"PR1-0002"}
    assert _belongs(header, ["PR1", "A-EUR", "PR1-0002", "F-2"], keys, "A-EUR")
    assert not _belongs(header, ["PR1", "A-EUR", "PR1-0001", "F-1"], keys, "A-EUR")
    assert not _belongs(header, ["PR1", "B-EUR", "PR1-0002", "F-9"], keys, "A-EUR")


def test_evidence_of_a_file_from_an_earlier_phase_is_found_and_stays_inside_it(tmp_path, monkeypatch):
    # A debit of July cites a run of June, whose file lives in the previous phase.
    monkeypatch.setattr(paths, "DB", tmp_path)
    monkeypatch.setattr(paths, "PKG", tmp_path / "pkg")
    for name in ("old", "new"):
        (tmp_path / name / "payment_runs").mkdir(parents=True)
        (tmp_path / name / "bank_transactions.csv.gz").write_bytes(b"")
    (tmp_path / "new" / "prior_phases").write_text("old\n")
    (tmp_path / "old" / "payment_runs" / "X_202506_0.csv").write_text("run_id\nPR1\n")
    (tmp_path / "secret.txt").write_text("no")
    run = RunData.__new__(RunData)
    run.phase, run.phase_dir = "new", tmp_path / "new"
    assert run.phase_file("payment_runs/X_202506_0.csv") == tmp_path / "old" / "payment_runs" / "X_202506_0.csv"
    assert run.phase_file("payment_runs/none.csv") is None
    assert run.phase_file("../secret.txt") is None


def test_only_the_served_run_is_marked_and_opened(env):
    _, runs, _ = env
    client = TestClient(create_app(store=Store(runs), warm=RUN))
    assert {r["runId"]: r["served"] for r in client.get("/api/runs").json()} == {RUN: True, "p-20250101-000000": False}
    assert not any(r["served"] for r in TestClient(create_app(store=Store(runs))).get("/api/runs").json())
    store = client.app.state.store
    assert store._runs.keys() <= {RUN}  # nothing else was opened by listing


def test_cases_sum_amount_eur_covers_the_whole_filter_not_the_page(api):
    everything = get(api, "/cases", size=2)
    assert len(everything["items"]) == 2 and everything["total"] == 5
    assert everything["sumAmountEur"] == 121000 + 50000 + 7500 + 30000 + 4000  # magnitudes, all five cases
    fallback = get(api, "/cases", status="fallback", size=1)
    assert fallback["sumAmountEur"] == 7500 + 4000 and len(fallback["items"]) == 1
    assert get(api, "/cases", status="done")["sumAmountEur"] == 0


def test_validation_errors_have_their_own_schema_with_row_and_message():
    schemas = create_app(store=Store(__import__("pathlib").Path("/none"))).openapi()["components"]["schemas"]
    issue = schemas["ValidationResult"]["properties"]["errors"]["items"]["$ref"].rsplit("/", 1)[1]
    assert issue != "ValidationError" and set(schemas[issue]["properties"]) == {"row", "message"}
    assert {"loc", "msg"} <= set(schemas["ValidationError"]["properties"])  # FastAPI's own, untouched
