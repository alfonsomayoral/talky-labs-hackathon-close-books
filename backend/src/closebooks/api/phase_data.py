"""The package of one phase (db/<phase>/ and its masters) as DuckDB tables, built the first time it is asked for."""
from __future__ import annotations

import os
import re
import threading

import duckdb

from ..paths import masters_dir, phase_dir
from .sqlutil import create_party, read_csv

DETAIL_FOLDERS = {"direct_debit_batches": "directDebitBatch", "card_settlements": "cardSettlement",
                  "cheque_deposits": "chequeDeposit", "payment_runs": "paymentRun"}
PDF_KINDS = {"ARI": "invoicePdf", "API": "invoicePdf", "ARC": "creditNotePdf", "APC": "creditNotePdf",
             "PF": "proformaPdf", "NOTICE": "bankAccountNotice"}
PARTY_ID = re.compile(r"^[CS][A-Z]{2}\d{2}\d+$")
CENTS = "CAST(round(CAST({} AS DOUBLE) * 100) AS BIGINT)"


def _norm(number: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", number).upper()


class PhaseData:
    def __init__(self, name: str):
        self.name = name
        self.dir = phase_dir(name)
        self.masters = masters_dir(self.dir)
        self.con = duckdb.connect()
        create_party(self.con, self.masters)
        self.lock = threading.RLock()
        self._items = self._accounts = self._documents = self._detail_files = None

    def cursor(self):
        return self.con.cursor()

    # ── items ────────────────────────────────────────────────────────────────

    def ensure_items(self) -> None:
        with self.lock:
            if self._items:
                return
            d, cents = self.dir, CENTS.format
            parts = []
            if (d / "ar_invoices.csv.gz").exists():
                parts.append(f"""SELECT item_id, 'ARI' AS item_type, entity, document_number, customer_id AS party_id,
                    customer_name AS party_name, issue_date, due_date, currency, {cents("total_amount")} AS total,
                    NULL AS related_document, customer_po AS reference FROM {read_csv(d / "ar_invoices.csv.gz")}""")
            if (d / "ap_invoices.csv.gz").exists():
                parts.append(f"""SELECT item_id, 'API', entity, supplier_invoice_number, supplier_id, supplier_name,
                    issue_date, due_date, currency, {cents("total_amount")}, NULL, our_po
                    FROM {read_csv(d / "ap_invoices.csv.gz")}""")
            if (d / "credit_notes.csv.gz").exists():
                parts.append(f"""SELECT item_id, substr(item_id, 1, 3), entity, document_number, party_id, party_name,
                    issue_date, NULL, currency, {cents("total_amount")}, related_document, reason
                    FROM {read_csv(d / "credit_notes.csv.gz")}""")
            self.con.execute("CREATE TABLE issued AS " + " UNION ALL ".join(parts))
            if (d / "open_items_at_start.csv.gz").exists():
                self.con.execute(f"""CREATE TABLE opening AS SELECT item_id, item_type, entity, party_id,
                    document_number, issue_date, due_date, currency, {cents("total_amount")} AS total,
                    {cents("open_amount")} AS open FROM {read_csv(d / "open_items_at_start.csv.gz")}""")
            else:
                self.con.execute("CREATE TABLE opening (item_id VARCHAR, item_type VARCHAR, entity VARCHAR, "
                                 "party_id VARCHAR, document_number VARCHAR, issue_date VARCHAR, due_date VARCHAR, "
                                 "currency VARCHAR, total BIGINT, open BIGINT)")
            self.con.execute("""CREATE TABLE items AS
                SELECT u.*, strip_accents(lower(concat_ws(' ', u."itemId", u."documentNumber", u."partyName")))
                       AS "_search" FROM (
                  SELECT i.item_id AS "itemId", i.item_type AS "itemType", i.entity,
                         i.document_number AS "documentNumber", i.party_id AS "partyId",
                         coalesce(i.party_name, p.name) AS "partyName", i.issue_date AS "issueDate",
                         i.due_date AS "dueDate", i.currency, i.total AS "totalCents", o.open AS "openAtStartCents",
                         i.related_document AS "relatedDocument", i.reference
                  FROM issued i LEFT JOIN opening o USING (item_id) LEFT JOIN party p ON p."partyId" = i.party_id
                  UNION ALL
                  SELECT o.item_id, o.item_type, o.entity, o.document_number, o.party_id, p.name, o.issue_date,
                         o.due_date, o.currency, o.total, o.open, NULL, NULL
                  FROM opening o LEFT JOIN party p ON p."partyId" = o.party_id
                  WHERE o.item_id NOT IN (SELECT item_id FROM issued)) u""")
            self.con.execute("DROP TABLE issued")
            self.con.execute("DROP TABLE opening")
            self._items = True

    # ── accounts ─────────────────────────────────────────────────────────────

    def accounts(self) -> list[dict]:
        """Master accounts plus the ones seen in the bank lines, with format periods and totals."""
        with self.lock:
            if self._accounts is None:
                self._accounts = self._build_accounts()
            return self._accounts

    def _build_accounts(self) -> list[dict]:
        c = self.cursor()
        bank = read_csv(self.dir / "bank_transactions.csv.gz")
        seen = {r[0]: r for r in c.execute(f"""SELECT account_id, any_value(entity), any_value(bank),
            any_value(currency), count(*), sum(CASE WHEN CAST(amount AS DOUBLE) > 0 THEN
            CAST(round(CAST(amount AS DOUBLE) * 100) AS BIGINT) ELSE 0 END),
            sum(CASE WHEN CAST(amount AS DOUBLE) < 0 THEN -CAST(round(CAST(amount AS DOUBLE) * 100) AS BIGINT)
            ELSE 0 END), min(booking_date), max(booking_date) FROM {bank} GROUP BY 1""").fetchall()}
        periods: dict[str, list[tuple]] = {}
        for row in c.execute(f"SELECT account_id, statement_format, min(booking_date) FROM {bank} GROUP BY 1, 2 "
                             f"ORDER BY 1, 3").fetchall():
            periods.setdefault(row[0], []).append(row[1:])
        master = c.execute(f"SELECT account_id, entity, bank, bank_name, currency, iban, purpose, statement_format, "
                           f"opened FROM {read_csv(self.masters / 'bank_accounts.csv')}").fetchall()
        out = []
        for acc, entity, bank_code, bank_name, currency, iban, purpose, fmt, opened in master:
            out.append(self._account(acc, entity, bank_code, bank_name, currency, iban, purpose, True,
                                     periods.get(acc) or [(fmt, opened or "")], seen.get(acc)))
        in_master = {m[0] for m in master}
        for acc, row in seen.items():
            if acc not in in_master:
                out.append(self._account(acc, row[1], row[2], None, row[3], None, None, False, periods[acc], row))
        return sorted(out, key=lambda a: a["accountId"])

    @staticmethod
    def _account(acc, entity, bank, bank_name, currency, iban, purpose, in_master, periods, seen) -> dict:
        _, _, _, _, count, inflow, outflow, first, last = seen or (None, None, None, None, 0, 0, 0, None, None)
        formats = [{"format": f, "from": start, "to": None} for f, start in periods]
        for prev, nxt in zip(formats, formats[1:], strict=False):
            prev["to"] = nxt["from"]
        return {"accountId": acc, "entity": entity, "bank": bank, "bankName": bank_name, "currency": currency,
                "iban": iban, "purpose": purpose, "inMaster": in_master, "formats": formats, "txns": count,
                "inflowCents": inflow or 0, "outflowCents": outflow or 0, "netCents": (inflow or 0) - (outflow or 0),
                "firstDate": first, "lastDate": last, "reconciledRate": None}

    # ── documents and detail files (file listings, cached) ───────────────────

    def documents(self) -> list[dict]:
        with self.lock:
            if self._documents is None:
                self._documents = self._scan_documents()
            return self._documents

    def _scan_documents(self) -> list[dict]:
        rows = []
        for folder in ("remittance_advices", "pdfs"):
            base = self.dir / folder
            if not base.is_dir():
                continue
            for entity_dir in sorted(p for p in base.iterdir() if p.is_dir()):
                for f in sorted(os.scandir(entity_dir), key=lambda e: e.name):
                    if f.is_file():
                        rows.append(self._document_row(folder, entity_dir.name, f.name))
        self._resolve_pdf_parties(rows)
        return rows

    def _document_row(self, folder: str, entity: str, name: str) -> dict:
        stem, _, ext = name.rpartition(".")
        tokens = stem.split("_")
        base = {"path": f"{folder}/{entity}/{name}", "entity": entity, "format": ext.lower(), "name": name,
                "date": None, "partyName": None, "_party": None, "_number": None}
        if folder == "remittance_advices":
            date = tokens[1] if len(tokens) > 1 and re.fullmatch(r"\d{8}", tokens[1]) else None
            return {**base, "kind": "remittanceAdvice", "date": f"{date[:4]}-{date[4:6]}-{date[6:]}" if date else None}
        kind = PDF_KINDS.get(tokens[0], "invoicePdf")
        party = next((t for t in tokens[1:] if PARTY_ID.match(t)), None)
        date = tokens[-1] if tokens[0] == "NOTICE" and re.fullmatch(r"\d{8}", tokens[-1]) else None
        number = tokens[-1] if tokens[0] in ("ARI", "ARC", "PF") else None
        return {**base, "kind": kind, "_party": party, "_number": number,
                "date": f"{date[:4]}-{date[4:6]}-{date[6:]}" if date else None}

    def _resolve_pdf_parties(self, rows: list[dict]) -> None:
        """Party and issue date of a PDF: from its name, or from the item whose number its name carries."""
        self.ensure_items()
        wanted = sorted({r["_number"] for r in rows if r["_number"]})
        by_number: dict[str, tuple] = {}
        if wanted:
            for norm, party, issued in self.cursor().execute(
                'SELECT regexp_replace("documentNumber", \'[^A-Za-z0-9]\', \'\', \'g\') AS n, any_value("partyName"), '
                'any_value("issueDate") FROM items WHERE n IN (SELECT unnest(?)) GROUP BY 1', [wanted]
            ).fetchall():
                by_number[norm.upper()] = (party, issued)
        names = dict(self.cursor().execute('SELECT "partyId", name FROM party').fetchall())
        for r in rows:
            if r["_party"]:
                r["partyName"] = names.get(r["_party"])
            elif r["_number"] and r["_number"].upper() in by_number:
                r["partyName"], r["date"] = by_number[r["_number"].upper()]
            del r["_party"], r["_number"]

    def detail_files(self) -> list[dict]:
        with self.lock:
            if self._detail_files is None:
                self._detail_files = self._scan_detail_files()
            return self._detail_files

    def _scan_detail_files(self) -> list[dict]:
        out = []
        for folder, kind in DETAIL_FOLDERS.items():
            for f in sorted((self.dir / folder).glob("*.csv")):
                tokens = f.stem.split("_")
                month = next((t for t in tokens if re.fullmatch(r"\d{6}", t)), None)
                with f.open("rb") as handle:
                    lines = sum(chunk.count(b"\n") for chunk in iter(lambda: handle.read(1 << 20), b""))
                out.append({"path": f"{folder}/{f.name}", "kind": kind, "entity": tokens[0],
                            "month": f"{month[:4]}-{month[4:]}" if month else None, "rows": max(lines - 1, 0)})
        return out

