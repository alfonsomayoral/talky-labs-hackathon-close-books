"""One run opened in memory: the run folder, the phase's bank lines and masters as DuckDB tables.

Built once when the run is first opened (a few seconds on LIVE) so every listing is a table scan.
Human decisions are overlaid on `cases.status` and `tx."caseStatus"` and re-synced after each write.
"""
from __future__ import annotations

import threading
from pathlib import Path

import duckdb
import orjson

from ..load import prior_dirs
from ..paths import masters_dir, phase_dir
from .fsafe import safe_join
from .human import HumanFiles, answered_questions, apply_outbox, case_statuses, read_jsonl
from .sqlutil import create_party, lit, read_csv

QUEUE = ("needs_review", "question", "fallback")
EXPLANATION_COLUMNS = (
    "{'bankTxnId':'VARCHAR','itemId':'VARCHAR','amountCents':'BIGINT','currency':'VARCHAR','category':'VARCHAR',"
    "'exception':'VARCHAR','rule':'VARCHAR','confidence':'DOUBLE','partyId':'VARCHAR','reference':'VARCHAR',"
    "'sources':'STRUCT(kind VARCHAR, ref VARCHAR, label VARCHAR)[]',"
    "'candidates':'STRUCT(itemId VARCHAR, amountCents BIGINT, currency VARCHAR, why VARCHAR)[]'}"
)
CASE_COLUMNS = (
    "{'caseId':'VARCHAR','kind':'VARCHAR','status':'VARCHAR','priority':'BIGINT','entity':'VARCHAR',"
    "'bankTxnId':'VARCHAR','partyId':'VARCHAR','itemIds':'VARCHAR[]','amountCents':'BIGINT','currency':'VARCHAR',"
    "'amountEur':'BIGINT','bookingDate':'VARCHAR','summary':'VARCHAR','suggestedAction':'VARCHAR',"
    "'questionId':'VARCHAR','draftId':'VARCHAR','rule':'VARCHAR','createdAt':'VARCHAR'}"
)
OPEN_ITEM_TYPES = {
    "itemId": "VARCHAR", "itemType": "VARCHAR", "entity": "VARCHAR", "partyId": "VARCHAR",
    "documentNumber": "VARCHAR", "issueDate": "VARCHAR", "dueDate": "VARCHAR", "currency": "VARCHAR",
    "totalCents": "BIGINT", "openAtStartCents": "BIGINT", "appliedCents": "BIGINT", "openAtEndCents": "BIGINT",
    "status": "VARCHAR", "history": "VARCHAR",
}


def _json(path: Path, columns: str) -> str:
    """read_json with a fixed schema: a nearly empty file must not change the column types."""
    return f"read_json({lit(path)}, format='newline_delimited', columns={columns})"


class RunData:
    def __init__(self, run_dir: Path):
        self.dir = run_dir
        self.id = run_dir.name
        self.meta: dict = orjson.loads((run_dir / "run.json").read_bytes())
        self.phase: str = self.meta["phase"]
        self.phase_dir = phase_dir(self.phase)
        self.human = HumanFiles(run_dir)
        self.write_lock = threading.Lock()
        self.con = duckdb.connect()
        self._build()
        self.sync_status()

    def cursor(self) -> duckdb.DuckDBPyConnection:
        return self.con.cursor()

    def phase_file(self, relative: str) -> Path | None:
        """A document of the phase or of an earlier one: rules cite files of the months before the phase starts."""
        for folder in (self.phase_dir, *prior_dirs(self.phase_dir, self.phase)):
            path = safe_join(folder, relative)
            if path is not None and path.is_file():
                return path
        return None

    # ── build ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        c, masters = self.con, masters_dir(self.phase_dir)
        c.execute(f"CREATE TABLE fx AS SELECT CAST(date AS DATE) AS date, currency, "
                  f"CAST(units_per_eur AS DOUBLE) AS rate FROM {read_csv(masters / 'fx_rates.csv')}")
        c.execute(f"CREATE TABLE entities AS SELECT entity AS code, legal_name AS name "
                  f"FROM {read_csv(masters / 'entities.csv')}")
        create_party(c, masters)
        c.execute(f"CREATE TABLE categories AS SELECT category FROM {read_csv(masters / 'categories.csv')}")
        c.execute(f"""CREATE TABLE bank AS
            SELECT t.bank_txn_id AS "bankTxnId", t.account_id AS "accountId", t.entity, t.bank,
                   t.statement_format AS "statementFormat", t.statement_file AS "statementFile",
                   t.booking_date AS "bookingDate", t.value_date AS "valueDate", t.amount_cents AS "amountCents",
                   t.currency, t.bank_code AS "bankCode", t.bank_subcode AS "bankSubcode", t.ref1, t.ref2, t.text,
                   t.counterparty_name AS "counterpartyName", t.counterparty_account AS "counterpartyAccount",
                   t.end_to_end_id AS "endToEndId", t.remittance_info AS "remittanceInfo",
                   t.orig_cents AS "origAmountCents", t.orig_currency AS "origCurrency",
                   CASE WHEN t.currency = 'EUR' THEN t.amount_cents
                        ELSE CAST(round(t.amount_cents / coalesce(fx.rate, 1.0)) AS BIGINT) END AS "amountEur"
            FROM (SELECT *, CAST(round(CAST(amount AS DOUBLE) * 100) AS BIGINT) AS amount_cents,
                         CAST(round(CAST(orig_amount AS DOUBLE) * 100) AS BIGINT) AS orig_cents,
                         CAST(booking_date AS DATE) AS d
                  FROM {read_csv(self.phase_dir / 'bank_transactions.csv.gz')}) t
            ASOF LEFT JOIN fx ON t.currency = fx.currency AND t.d >= fx.date""")
        asof = c.execute('SELECT max(CAST("bookingDate" AS DATE)) FROM bank').fetchone()[0]
        self.as_of = asof.isoformat() if asof else None
        c.execute(f"""CREATE TABLE cases AS
            SELECT k.* REPLACE (abs(k."amountCents") AS "amountCents", abs(k."amountEur") AS "amountEur"),
                   k.status AS "baseStatus", p.name AS "partyName",
                   strip_accents(lower(concat_ws(' ', k."caseId", k.summary, p.name))) AS "_search"
            FROM {_json(self.dir / 'cases.jsonl.gz', CASE_COLUMNS)} k
            LEFT JOIN party p ON p."partyId" = k."partyId\"""")
        self._build_open_items()
        c.execute(f"""CREATE TABLE rows AS
            SELECT r.rn AS "rowNo", r."bankTxnId", r."itemId", r."amountCents", r.currency, r.category, r.exception,
                   r.rule, r.confidence, r."partyId", r.reference, r.sources, r.candidates, b.entity,
                   b."bookingDate",
                   CASE WHEN r."amountCents" IS NULL THEN NULL WHEN r.currency = 'EUR' THEN r."amountCents"
                        ELSE CAST(round(r."amountCents" / coalesce(fx.rate, 1.0)) AS BIGINT) END AS "amountEur"
            FROM (SELECT row_number() OVER () AS rn, * FROM
                  {_json(self.dir / 'explanations.jsonl.gz', EXPLANATION_COLUMNS)}) r
            LEFT JOIN (SELECT "bankTxnId", entity, "bookingDate", CAST("bookingDate" AS DATE) AS d FROM bank) b
                   ON b."bankTxnId" = r."bankTxnId"
            ASOF LEFT JOIN fx ON r.currency = fx.currency AND b.d >= fx.date""")
        self._build_tx()

    def _build_open_items(self) -> None:
        path = self.dir / "state" / "open_items.parquet"
        if path.exists():
            self.con.execute(f"CREATE TABLE open_src AS SELECT * FROM read_parquet({lit(path)})")
        else:
            self.con.execute("CREATE TABLE open_src (" + ", ".join(f'"{k}" {v}' for k, v in OPEN_ITEM_TYPES.items())
                             + ")")
        as_of = f"CAST({'NULL' if self.as_of is None else repr(self.as_of)} AS DATE)"
        self.con.execute(f"""CREATE TABLE open_items AS
            WITH rate AS (SELECT currency, arg_max(rate, date) AS rate FROM fx
                          WHERE date <= CAST({as_of} AS DATE) GROUP BY currency)
            SELECT o.*, p.name AS "partyName",
                   CASE WHEN o.currency = 'EUR' THEN o."openAtEndCents"
                        ELSE CAST(round(o."openAtEndCents" / coalesce(rate.rate, 1.0)) AS BIGINT) END AS "openAtEndEur",
                   CASE WHEN o."dueDate" IS NULL OR o."openAtEndCents" <= 0 THEN 0
                        ELSE greatest(0, date_diff('day', CAST(o."dueDate" AS DATE),
                                                   CAST({as_of} AS DATE))) END AS "daysOverdue",
                   strip_accents(lower(concat_ws(' ', o."itemId", o."documentNumber", p.name))) AS "_search"
            FROM open_src o LEFT JOIN party p ON p."partyId" = o."partyId"
            LEFT JOIN rate ON rate.currency = o.currency""")

    def _build_tx(self) -> None:
        c = self.con
        c.execute("""CREATE TABLE first_row AS
            SELECT "bankTxnId", count(*) AS "rowCount", bool_or("itemId" IS NOT NULL) AS "hasItem",
                   arg_min(rule, "rowNo") AS rule, arg_min(confidence, "rowNo") AS confidence,
                   arg_min("partyId", "rowNo") FILTER (WHERE "partyId" IS NOT NULL) AS "partyId"
            FROM rows GROUP BY 1""")
        c.execute("""CREATE TABLE row_docs AS
            SELECT r."rowNo", r."bankTxnId", r."itemId", r."amountCents", r.currency, r.category, r.exception,
                   o."documentNumber" FROM rows r LEFT JOIN open_items o ON o."itemId" = r."itemId\"""")
        c.execute("""CREATE TABLE asg AS
            SELECT "bankTxnId", list(struct_pack(itemId := "itemId", documentNumber := "documentNumber",
                   amountCents := "amountCents", currency := currency, category := category,
                   exception := exception) ORDER BY "rowNo") AS assignments
            FROM (SELECT * FROM row_docs
                  QUALIFY row_number() OVER (PARTITION BY "bankTxnId" ORDER BY "rowNo") <= 5) GROUP BY 1""")
        c.execute("""CREATE TABLE doc_numbers AS
            SELECT "bankTxnId", string_agg("documentNumber", ' ') AS numbers FROM row_docs
            WHERE "documentNumber" IS NOT NULL GROUP BY 1""")
        c.execute("""CREATE TABLE case_of AS
            SELECT "bankTxnId", min("caseId") AS "caseId", arg_min(status, "caseId") AS "caseStatus"
            FROM cases WHERE "bankTxnId" IS NOT NULL GROUP BY 1""")
        c.execute("""CREATE TABLE tx AS
            SELECT b.*, coalesce(f.rule, 'NONE') AS rule, coalesce(f.confidence, 0.0) AS confidence,
                   f."partyId", p.name AS "partyName", k."caseId", k."caseStatus",
                   coalesce(f."rowCount", 0) AS "rowCount", coalesce(f."hasItem", false) AS "hasItem",
                   a.assignments,
                   strip_accents(lower(concat_ws(' ', b."bankTxnId", b.text, b."counterpartyName", n.numbers)))
                       AS "_search"
            FROM bank b LEFT JOIN first_row f ON f."bankTxnId" = b."bankTxnId"
            LEFT JOIN party p ON p."partyId" = f."partyId"
            LEFT JOIN case_of k ON k."bankTxnId" = b."bankTxnId"
            LEFT JOIN asg a ON a."bankTxnId" = b."bankTxnId"
            LEFT JOIN doc_numbers n ON n."bankTxnId" = b."bankTxnId\"""")
        for table in ("first_row", "row_docs", "asg", "doc_numbers", "case_of"):
            c.execute(f"DROP TABLE {table}")

    # ── human overlay ────────────────────────────────────────────────────────

    def sync_status(self) -> None:
        """Case status = the backend's, overridden by the latest decision of each case."""
        statuses = case_statuses(self.human.read("decisions.jsonl"))
        with self.write_lock:
            c = self.cursor()
            c.execute('UPDATE cases SET status = "baseStatus" WHERE status <> "baseStatus"')
            c.execute('UPDATE tx SET "caseStatus" = k."baseStatus" FROM cases k WHERE tx."caseId" = k."caseId" '
                      'AND tx."caseStatus" IS DISTINCT FROM k."baseStatus"')
            if statuses:
                c.execute('CREATE OR REPLACE TABLE decided("caseId" VARCHAR, status VARCHAR)')
                c.executemany("INSERT INTO decided VALUES (?, ?)", list(statuses.items()))
                c.execute('UPDATE cases SET status = d.status FROM decided d WHERE cases."caseId" = d."caseId"')
                c.execute('UPDATE tx SET "caseStatus" = d.status FROM decided d WHERE tx."caseId" = d."caseId"')

    def questions(self) -> list[dict]:
        answered = answered_questions(self.human.read("decisions.jsonl"))
        return [{**q, "status": "answered" if q["questionId"] in answered else "open"}
                for q in read_jsonl(self.dir / "questions.jsonl")]

    def drafts(self) -> list[dict]:
        return apply_outbox(read_jsonl(self.dir / "drafts.jsonl"), self.human.read("outbox.jsonl"))
