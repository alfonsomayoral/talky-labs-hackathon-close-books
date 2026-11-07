"""A minimal phase and run folder written to a tmp dir, so the API tests run without db/."""
from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

import duckdb

BANK_HEADER = ["bank_txn_id", "account_id", "entity", "bank", "statement_format", "statement_file", "booking_date",
               "value_date", "amount", "currency", "bank_code", "bank_subcode", "ref1", "ref2", "text",
               "counterparty_name", "counterparty_account", "end_to_end_id", "remittance_info", "orig_amount",
               "orig_currency"]
# id, account, entity, format, date, amount, currency, text, counterparty
BANK = [
    ("BT-1", "E1-BK-EUR", "E1", "n43", "2025-07-01", "1210.00", "EUR", "TRANSFER ACME INV FV1", "Acme Ñandú S.L."),
    ("BT-2", "E1-BK-EUR", "E1", "n43", "2025-07-02", "500.00", "EUR", "TRANSFER SPLIT PAYMENT", "Beta S.A."),
    ("BT-3", "E1-BK-EUR", "E1", "n43", "2025-07-03", "-75.00", "EUR", "COMISION MANTENIMIENTO", None),
    ("BT-4", "E1-BK-EUR", "E1", "n43", "2025-07-05", "300.00", "EUR", "INGRESO SIN REFERENCIA", "MARIA RUBIO"),
    ("BT-5", "E2-BK-USD", "E2", "camt053", "2025-07-06", "100.00", "USD", "DIRECT DEBIT BATCH B77", None),
    ("BT-6", "E1-BK-EUR", "E1", "n43", "2025-07-10", "-1210.00", "EUR", "DEVOLUCION RECIBO FV1", "Acme Ñandú S.L."),
    ("BT-7", "E2-BK-USD", "E2", "camt053", "2025-07-11", "-50.00", "USD", "BANK FEE", None),
    ("BT-8", "E1-BK-EUR", "E1", "camt053", "2025-07-12", "80.00", "EUR", "AVISO 8826032134", "Acme Ñandú S.L."),
    ("BT-9", "E1-BK-EUR", "E1", "camt053", "2025-07-12", "60.00", "EUR", "COBRO HABITUAL", "Gamma S.L."),
]


def _row(txn_id, item, amount, cur, rule, conf, party=None, ref=None, exc=None, cat=None, sources=(), cands=()):
    return {"bankTxnId": txn_id, "itemId": item, "amountCents": amount, "currency": cur, "category": cat,
            "exception": exc, "rule": rule, "confidence": conf, "partyId": party, "reference": ref,
            "sources": list(sources), "candidates": list(cands)}


ADVICE = "remittance_advices/E1/RA_20250712_ACME_1.txt"
BATCH = "direct_debit_batches/E2_B77_202507.csv"
EXPLANATIONS = [
    _row("BT-1", "ARI-1", 121000, "EUR", "REF-EXACT", 1.0, "C1", "FV1"),
    _row("BT-2", "ARI-2", 30000, "EUR", "PARTY-AMOUNT", 0.8, "C1", None, "PARTIAL",
         cands=[{"itemId": "ARI-3", "amountCents": 20000, "currency": "EUR", "why": "same amount"}]),
    _row("BT-2", "ARI-3", 20000, "EUR", "PARTY-AMOUNT", 0.8, "C1",
         cands=[{"itemId": "ARI-3", "amountCents": 20000, "currency": "EUR", "why": "same amount"}]),
    _row("BT-3", None, None, None, "FALLBACK-CATEGORY", 0.0, cat="BANK_FEES"),
    _row("BT-4", None, None, None, "FALLBACK-UNIDENTIFIED", 0.0, cat="UNIDENTIFIED", exc="UNIDENTIFIED"),
    _row("BT-5", "ARI-4", 10000, "USD", "FILE-DD-BATCH", 1.0, "C3", "B77",
         sources=[{"kind": "directDebitBatch", "ref": BATCH, "label": None}]),
    _row("BT-6", "ARI-1", 121000, "EUR", "REF-EXACT", 1.0, "C1", "FV1", "RETURNED"),
    _row("BT-7", None, None, None, "FALLBACK-CATEGORY", 0.0, cat="BANK_FEES"),
    _row("BT-8", "ARI-5", 8000, "EUR", "ADVICE-TXT", 1.0, "C1", "AVISO 8826032134",
         sources=[{"kind": "remittanceAdvice", "ref": ADVICE, "label": None},
                  {"kind": "pdf", "ref": "../../secret.txt", "label": None},
                  {"kind": "customer", "ref": "C1", "label": None}]),
    _row("BT-9", "ARI-5", 6000, "EUR", "MEMORY-RULE", 1.0, "C1", None,
         sources=[{"kind": "memoryRule", "ref": "MR-0001", "label": None}]),
    _row("BT-9", "ARI-3", 100, "EUR", "MEMORY-RULE", 1.0, "C2", None,
         sources=[{"kind": "memoryRule", "ref": "MR-0001", "label": None}]),
]


def _case(txn_id, kind, status, prio, entity, cents, cur, eur, date, summary, rule, party=None, question=None):
    return {"caseId": f"CASE-{txn_id}", "kind": kind, "status": status, "priority": prio, "entity": entity,
            "bankTxnId": txn_id, "partyId": party, "itemIds": [], "amountCents": cents, "currency": cur,
            "amountEur": eur, "bookingDate": date, "summary": summary, "suggestedAction": "review",
            "questionId": question, "draftId": None, "rule": rule, "createdAt": "2026-11-07T02:10:00+01:00"}


CASES = [
    _case("BT-2", "ambiguous_match", "needs_review", 2, "E1", 50000, "EUR", 50000, "2025-07-02", "Cobro dividido",
          "PARTY-AMOUNT", "C1"),
    # signed on purpose: older runs wrote signed amounts and the API must still report magnitudes
    _case("BT-3", "unknown_debit", "fallback", 3, "E1", -7500, "EUR", -7500, "2025-07-03", "Cargo de 75,00 EUR",
          "FALLBACK-CATEGORY"),
    _case("BT-4", "unidentified_receipt", "question", 1, "E1", 30000, "EUR", 30000, "2025-07-05",
          "Cobro de MARIA RUBIO sin tercero", "FALLBACK-UNIDENTIFIED", None, "Q-1"),
    _case("BT-7", "unknown_debit", "fallback", 3, "E2", 5000, "USD", 4000, "2025-07-11", "Cargo de 50,00 USD",
          "FALLBACK-CATEGORY"),
    {**_case("overdue-1", "overdue_customer", "needs_review", 2, "E1", 121000, "EUR", 121000, None,
             "Cliente vencido", None, "C1"), "caseId": "CASE-overdue-1", "bankTxnId": None},
]

QUESTION = {
    "questionId": "Q-1", "caseId": "CASE-BT-4", "bankTxnId": "BT-4", "entity": "E1",
    "question": "¿A qué factura corresponde?",
    "options": [{"id": "ARI-3", "label": "FV3"}, {"id": "none", "label": "Ninguna"}], "defaultOption": "none",
    "rulePreview": {"kind": "payer_is_customer", "payerName": "MARIA RUBIO", "partyId": "<la opción elegida>",
                    "description": "Cobros de MARIA RUBIO al cliente elegido"},
    "status": "open", "createdAt": "2026-11-07T02:10:00+01:00"}
DRAFTS = [{"draftId": f"D-{n}", "caseId": "CASE-overdue-1", "kind": "email_customer", "to": "a@b.example",
           "toName": "Acme", "partyId": "C1", "language": "es", "subject": "Facturas vencidas", "body": "Estimados",
           "attachments": [], "generatedBy": "claude-haiku-5-5", "status": "draft",
           "createdAt": "2026-11-07T02:10:00+01:00"} for n in (1, 2)]

# item, type, entity, party, doc, issue, due, currency, total, open_start, applied, open_end, status
OPEN_ITEMS = [
    ("ARI-1", "ARI", "E1", "C1", "FV1", "2025-04-01", "2025-06-01", "EUR", 121000, 121000, 0, 121000, "returned"),
    ("ARI-2", "ARI", "E1", "C1", "FV2", "2025-06-20", "2025-07-20", "EUR", 60000, 60000, 30000, 30000, "partial"),
    ("ARI-3", "ARI", "E1", "C2", "FV3", "2025-03-01", "2025-05-01", "EUR", 20000, 20000, 0, 20000, "open"),
    ("ARI-4", "ARI", "E2", "C3", "FV4", "2025-06-01", "2025-07-01", "USD", 10000, 10000, 10000, 0, "cleared"),
    ("ARI-5", "ARI", "E1", "C1", "FV5", "2025-06-01", "2025-07-01", "EUR", 14000, 14000, 14000, 0, "cleared"),
    ("API-1", "API", "E1", "S1", "SUP-9", "2025-06-01", "2025-06-30", "EUR", 5000, 5000, 0, 5000, "open"),
]


def _write_csv(path: Path, header: list[str], rows: list[list], compress: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if compress else open
    with opener(path, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _jsonl_gz(path: Path, records: list[dict]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.writelines(json.dumps(r) + "\n" for r in records)


def build_phase(db: Path, name: str = "p") -> Path:
    folder = db / name
    masters = folder / "masters"
    _write_csv(masters / "entities.csv", ["entity", "legal_name"], [["E1", "Uno S.A."], ["E2", "Dos Inc."]])
    _write_csv(masters / "bank_accounts.csv",
               ["account_id", "entity", "bank", "bank_name", "currency", "iban", "purpose", "statement_format",
                "opened"],
               [["E1-BK-EUR", "E1", "BK", "Banco K", "EUR", "ES00", "Cobros", "n43", ""],
                ["E1-BK-IDLE", "E1", "BK", "Banco K", "EUR", "ES11", "Sin uso", "n43", "2024-01-01"]])
    cust = ["customer_id", "entity", "name", "trade_name", "customer_type", "country", "tax_id", "iban",
            "sepa_mandate_id", "payment_terms", "invoice_currency", "group_id", "parent_customer_id", "created",
            "blocked_since"]
    _write_csv(masters / "customers.csv", cust, [
        ["C1", "E1", "Acme Ñandú S.L.", "", "KEY", "ES", "B1", "", "", "T30", "EUR", "G1", "C2", "2021-01-01", ""],
        ["C2", "E1", "Beta, S.A.", "", "KEY", "ES", "B2", "", "", "T30", "EUR", "G1", "", "2021-01-01", ""],
        ["C3", "E2", "Gamma Inc.", "", "SMB", "US", "B3", "", "", "T30", "USD", "", "", "2021-01-01", ""]])
    _write_csv(masters / "suppliers.csv", ["supplier_id", "entity", "name", "country", "tax_id", "supplier_type",
                                           "iban", "account_number", "payment_method", "payment_terms",
                                           "invoice_currency", "created", "blocked_since"],
               [["S1", "E1", "Proveedor Uno", "ES", "A1", "GOODS", "", "", "transfer", "T60", "EUR", "2021-01-01", ""]])
    _write_csv(masters / "categories.csv", ["category", "description", "gl_account"],
               [["BANK_FEES", "Comisiones", "626"], ["UNIDENTIFIED", "Sin identificar", "0"]])
    _write_csv(masters / "fx_rates.csv", ["date", "currency", "units_per_eur", "source"],
               [["2025-06-30", "USD", "1.2500", "ECB"], ["2025-07-10", "USD", "1.1000", "ECB"]])
    _write_csv(folder / "bank_transactions.csv.gz", BANK_HEADER, [
        [t, acc, ent, "BK", fmt, f"{name}/bank_statements/{acc}/x", date, date, amount, cur, "", "", "REF1", "",
         text, cp or "", "", "", "", "", ""] for t, acc, ent, fmt, date, amount, cur, text, cp in BANK],
        compress=True)
    _write_csv(folder / "ar_invoices.csv.gz",
               ["item_id", "entity", "document_number", "issue_date", "due_date", "customer_id", "customer_name",
                "currency", "net_amount", "tax_amount", "total_amount", "payment_terms", "customer_po",
                "payment_method"],
               [["ARI-1", "E1", "FV1", "2025-04-01", "2025-06-01", "C1", "Acme Ñandú S.L.", "EUR", "1000", "210",
                 "1210.00", "T30", "PO-7", "transfer"],
                ["ARI-4", "E2", "FV4", "2025-06-01", "2025-07-01", "C3", "Gamma Inc.", "USD", "100", "0", "100.00",
                 "T30", "", "dd"]], compress=True)
    _write_csv(folder / "ap_invoices.csv.gz",
               ["item_id", "entity", "supplier_id", "supplier_name", "supplier_invoice_number", "issue_date",
                "due_date", "currency", "net_amount", "tax_amount", "total_amount", "payment_terms", "our_po",
                "payment_method"],
               [["API-1", "E1", "S1", "Proveedor Uno", "SUP-9", "2025-06-01", "2025-06-30", "EUR", "50", "0",
                 "50.00", "T60", "", "transfer"]], compress=True)
    _write_csv(folder / "credit_notes.csv.gz",
               ["item_id", "side", "entity", "document_number", "issue_date", "party_id", "party_name", "currency",
                "net_amount", "tax_amount", "total_amount", "related_document", "reason"],
               [["ARC-1", "AR", "E1", "AB1", "2025-05-01", "C1", "Acme Ñandú S.L.", "EUR", "10", "0", "10.00", "FV1",
                 "Abono"]], compress=True)
    _write_csv(folder / "open_items_at_start.csv.gz",
               ["item_id", "item_type", "entity", "party_id", "document_number", "issue_date", "due_date",
                "currency", "total_amount", "open_amount"],
               [["ARI-1", "ARI", "E1", "C1", "FV1", "2025-04-01", "2025-06-01", "EUR", "1210.00", "1210.00"],
                ["ARI-OLD", "ARI", "E1", "C2", "FV0", "2021-01-01", "2021-02-01", "EUR", "5.00", "5.00"]],
               compress=True)
    (folder / "remittance_advices" / "E1").mkdir(parents=True)
    (folder / ADVICE).write_text("Aviso de pago 8826032134\nFV25-1 1.210,00\n", encoding="utf-8")
    # batch ids repeat across entities: B77 also exists on E1's account, with other lines
    _write_csv(folder / BATCH, ["batch_id", "account_id", "end_to_end_id", "mandate_id", "amount"],
               [["B77", "E2-BK-USD", "B77-0001", "VTM-1", "100.00"], ["B77", "E1-BK-EUR", "B77-0001", "VTM-1", "9.00"],
                ["B99", "E2-BK-USD", "B99-0001", "VTM-2", "5.00"]])
    (folder.parent / "secret.txt").write_text("TOP SECRET", encoding="utf-8")
    return folder


def build_run(runs: Path, run_id: str, phase: str = "p", created: str = "2026-11-07T02:10:00+01:00",
              score: dict | None = None) -> Path:
    run = runs / run_id
    (run / "facts").mkdir(parents=True)
    (run / "state").mkdir()
    meta = {"runId": run_id, "phase": phase, "dataDir": "db/p", "createdAt": created, "gitCommit": "abc1234",
            "durationMs": 3000, "stages": {"load": 1000, "rules": 500, "resolve": 500, "output": 1000},
            "txns": len(BANK), "rows": len(EXPLANATIONS), "csvBytes": 1000, "byRule": {}, "byException": {},
            "byCategory": {}, "cases": {"fallback": 2}, "models": {"claude-haiku-5-5": {
                "calls": 3, "inputTokens": 10, "outputTokens": 5, "costUsd": 0.25}},
            "memoryRulesApplied": 1, "score": score}
    (run / "run.json").write_text(json.dumps(meta))
    _jsonl_gz(run / "explanations.jsonl.gz", EXPLANATIONS)
    _jsonl_gz(run / "cases.jsonl.gz", CASES)
    (run / "questions.jsonl").write_text(json.dumps(QUESTION) + "\n")
    (run / "drafts.jsonl").write_text("".join(json.dumps(d) + "\n" for d in DRAFTS))
    con = duckdb.connect()
    values = ", ".join("(" + ", ".join(repr(v) for v in row[:12]) + f", '{row[12]}', '[]')" for row in OPEN_ITEMS)
    con.execute(f"""COPY (SELECT * FROM (VALUES {values}) t(itemId, itemType, entity, partyId, documentNumber,
        issueDate, dueDate, currency, totalCents, openAtStartCents, appliedCents, openAtEndCents, status, history))
        TO '{run / "state" / "open_items.parquet"}' (FORMAT parquet)""")
    con.execute(f"""COPY (SELECT '{ADVICE}' AS docPath, 'remittanceAdvice' AS docKind, 'E1' AS entity,
        'ACME' AS payerName, NULL::VARCHAR AS receivedDate, '8826032134' AS paymentRef, NULL::VARCHAR AS paymentDate,
        NULL::BIGINT AS paymentTotalCents, 'EUR' AS currency, 1::BIGINT AS lineNo, 'FV25-1' AS documentNumber,
        'FV251' AS documentNumberNorm, 121000::BIGINT AS grossCents, NULL::BIGINT AS deductionCents,
        NULL::VARCHAR AS reason, 121000::BIGINT AS paidCents, NULL::VARCHAR AS customerPo, NULL::VARCHAR AS voucher,
        NULL::VARCHAR AS clause, NULL::VARCHAR AS clauseValue, 'parser' AS method, NULL::VARCHAR AS model,
        'k1' AS cacheKey) TO '{run / "facts" / "documents.parquet"}' (FORMAT parquet)""")
    con.execute(f"""COPY (SELECT * FROM (VALUES
        ('BT-1', 'C1', 'customer', 'ACME NANDU', 'name', 0.9::DOUBLE, '[{{"partyId": "C2", "score": 0.4}}]'),
        ('BT-9', 'C1', 'customer', 'GAMMA', 'name', 0.9::DOUBLE, '[]'))
        t(bankTxnId, partyId, partyKind, payerName, how, confidence, alternatives))
        TO '{run / "facts" / "parties.parquet"}' (FORMAT parquet)""")
    return run
