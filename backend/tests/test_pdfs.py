from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

from closebooks.documents import pdfs
from closebooks.documents.pdfs import (
    PdfError,
    clauses_frame,
    clauses_from_text,
    parse_pdf,
    phase_clauses,
    residue,
    unextracted_hints,
)

FIXTURES = Path(__file__).parent / "fixtures" / "pdfs"


def clauses(name: str, doc_date: str | None = None) -> list[tuple[str, dict]]:
    return [(c.kind, c.value) for c in parse_pdf(FIXTURES / f"{name}.pdf", doc_date)]


# --- instalments, retention, advance -------------------------------------------------------------------------------

def test_instalments_in_english_give_the_plan_with_days_and_amounts_in_cents():
    assert clauses("instalments_en") == [("instalments", {
        "n": 3, "days": [30, 60, 90], "amounts": [185483, 185483, 185483], "currency": "CAD"})]


def test_instalments_in_spanish_keep_the_last_instalment_as_printed():
    assert clauses("instalments_es") == [("instalments", {
        "n": 2, "days": [30, 60], "amounts": [974853, 974854], "currency": "MXN"})]


def test_retention_in_english_reads_the_release_date_closest_to_a_year_after_the_invoice():
    assert clauses("retention_en", "2024-04-02") == [("retention", {
        "pct": 5, "amountCents": 294104, "currency": "EUR", "releaseDate": "2025-04-02", "payableCents": 5587986})]


def test_retention_in_spanish_wrapped_over_two_lines_with_decimal_comma():
    assert clauses("retention_es", "2022-05-05") == [("retention", {
        "pct": 5, "amountCents": 97400, "currency": "USD", "releaseDate": "2023-05-05", "payableCents": 1850619})]


def test_advance_in_english_names_the_proforma_and_the_net_due():
    assert clauses("advance_en") == [("advance_deduction", {
        "amountCents": 59180, "proforma": "PF23-1300011", "netDueCents": 138089, "currency": "USD"})]


def test_advance_in_spanish_names_the_proforma_and_the_net_due():
    assert clauses("advance_es") == [("advance_deduction", {
        "amountCents": 104678, "proforma": "PF24-0100001", "netDueCents": 157019, "currency": "MXN"})]


# --- replaces, service month ---------------------------------------------------------------------------------------

def test_replaces_in_english_on_a_french_invoice():
    assert clauses("replaces_en", "2021-11-17") == [("replaces", {"replaces": "FA210222934", "date": "2021-11-12"})]


def test_replaces_in_spanish_with_a_dashed_number():
    assert clauses("replaces_es", "2022-10-28") == [("replaces", {"replaces": "A01-2211305", "date": "2022-10-25"})]


def test_service_month_in_english():
    assert clauses("service_month_en") == [("service_month", {"month": 12, "year": 2024})]


def test_service_month_in_spanish_ignores_the_table_row_where_the_month_is_cut_off():
    assert clauses("service_month_es") == [("service_month", {"month": 2, "year": 2023})]


# --- rappel, credit note refund, factoring -------------------------------------------------------------------------

@pytest.mark.parametrize("name, kind, quarter, year, pct, base, currency", [
    ("rappel_offset_en", "rappel_offset", 3, 2023, 2.0, 3961950, "USD"),
    ("rappel_payout_en", "rappel_payout", 1, 2025, 1.5, 1696446, "USD"),
    ("rappel_offset_es", "rappel_offset", 2, 2021, 2.0, 4302003, "USD"),
    ("rappel_payout_es", "rappel_payout", 4, 2021, 3.0, 445495, "USD"),
])
def test_rappel_is_offset_or_paid_out_in_both_languages(name, kind, quarter, year, pct, base, currency):
    assert clauses(name) == [(kind, {"quarter": quarter, "year": year, "pct": pct, "baseCents": base,
                                      "currency": currency})]


@pytest.mark.parametrize("name, mode", [
    ("credit_offset_en", "offset"), ("credit_refund_en", "refund"),
    ("credit_offset_es", "offset"), ("credit_refund_es", "refund"),
])
def test_supplier_credit_note_is_offset_or_refunded(name, mode):
    assert clauses(name) == [("credit_refund", {"mode": mode})]


@pytest.mark.parametrize("name, factor", [
    ("factored_en", "Confirming Peñalara"), ("factored_es", "Ribagorza Confirming")])
def test_factored_invoice_names_the_factor_without_its_trailing_dot(name, factor):
    assert clauses(name) == [("factored", {"factor": factor})]


# --- bank account notices ------------------------------------------------------------------------------------------

def test_notice_for_direct_debits_has_the_new_and_old_iban_the_date_and_the_mandate():
    assert clauses("notice_es_debit", "2024-11-26") == [("new_iban", {
        "iban": "ES6094553676547659234999", "previous": "ES4894701486781616756321", "from": "2024-12-06",
        "via": "direct_debit", "mandate": "VTM-ES-0006421"})]


def test_notice_for_payments_in_spanish():
    assert clauses("notice_es_payment", "2025-02-14") == [("new_iban", {
        "iban": "ES4994279993282609202752", "previous": "ES0494505938665469866773", "from": "2025-02-24",
        "via": "payment"})]


def test_notice_for_payments_in_english():
    assert clauses("notice_en", "2023-03-12") == [("new_iban", {
        "iban": "PT08944053240930376394569", "previous": "PT35944713152023603739879", "from": "2023-03-22",
        "via": "payment"})]


# --- precision: no clause where the document has none --------------------------------------------------------------

@pytest.mark.parametrize("name", ["plain_invoice", "return_credit_note", "proforma"])
def test_documents_without_a_clause_give_none(name):
    assert clauses(name) == []


def test_a_reference_in_the_description_is_not_a_service_month():
    assert clauses_from_text("Cuota de mantenimiento y servicio técnico correspondiente a 1 16.449,20 16.449,20") == []


def test_a_hint_without_the_fixed_sentence_is_reported_as_unextracted():
    text = "Forma de pago: 3 vencimientos según contrato. Retención del 10 % hasta la recepción."
    assert clauses_from_text(text) == []
    assert unextracted_hints(text, []) == {"instalments", "retention"}


def test_an_extracted_clause_is_not_an_unextracted_hint():
    text = " ".join(
        "Payment terms: 2 instalments at 30/60 days (10.00 / 10.00 EUR).".split())
    found = clauses_from_text(text)
    assert [c.kind for c in found] == ["instalments"]
    assert unextracted_hints(text, found) == set()


def test_unreadable_pdf_raises_pdf_error(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 truncated")
    with pytest.raises(PdfError):
        parse_pdf(bad)


# --- the phase: index, prior phases, failures, frame ---------------------------------------------------------------

INDEX = "file,document_type,document_number,entity,party_id,document_date\n"


def pdf_folder(root: Path, rows: list[tuple[str, str, str, str, str, str]], fixtures: dict[str, str]) -> None:
    (root / "pdfs").mkdir(parents=True)
    lines = []
    for file, kind, number, entity, party, date in rows:
        target = root / "pdfs" / file
        target.parent.mkdir(parents=True, exist_ok=True)
        source = fixtures.get(file)
        if source is None:
            target.write_bytes(b"not a pdf")
        else:
            shutil.copy(FIXTURES / f"{source}.pdf", target)
        lines.append(f"{file},{kind},{number},{entity},{party},{date}")
    (root / "pdfs" / "index.csv").write_text(INDEX + "\n".join(lines) + "\n")


def items(rows: list[tuple[str, str, str, str, int]]) -> pl.DataFrame:
    schema = {"item_id": pl.String, "item_type": pl.String, "entity": pl.String, "document_number": pl.String,
              "open_cents": pl.Int64}
    return pl.DataFrame(rows, schema=schema, orient="row")


@pytest.fixture
def tiny_phase(tmp_path):
    prior, here = tmp_path / "prior", tmp_path / "here"
    pdf_folder(prior, [
        ("MX01/ARI_open.pdf", "invoice", "A01-2207305", "MX01", "C1", "2022-06-30"),
        ("MX01/ARI_closed.pdf", "invoice", "A01-2204954", "MX01", "C2", "2022-05-05"),
        ("MX01/PF.pdf", "proforma", "PF23-0600010", "US01", "C3", "2023-10-06"),
    ], {"MX01/ARI_open.pdf": "instalments_es", "MX01/ARI_closed.pdf": "retention_es", "MX01/PF.pdf": "proforma"})
    pdf_folder(here, [
        ("US01/ARC_1.pdf", "credit_note", "CM072300636", "US01", "C4", "2023-10-06"),
        ("US01/API_1.pdf", "supplier_invoice", "INV0002200", "US01", "S1", "2023-02-01"),
        ("PT01/NOTICE_1.pdf", "bank_account_notice", "N-1", "PT01", "C5", "2023-03-12"),
        ("US01/broken.pdf", "invoice", "X-1", "US01", "C6", "2023-01-01"),
    ], {"US01/ARC_1.pdf": "rappel_offset_en", "US01/API_1.pdf": "factored_en", "PT01/NOTICE_1.pdf": "notice_en"})
    frame = items([
        ("ARI-1", "ARI", "MX01", "A01-2207305", 1948707), ("ARI-2", "ARI", "MX01", "A01-2204954", 0),
        ("ARC-1", "ARC", "US01", "CM072300636", 79239), ("API-1", "API", "US01", "INV0002200", 390031),
    ])
    return SimpleNamespace(name="tiny", dir=here, prior=[prior], items=frame)


def test_phase_clauses_reads_the_phase_and_only_the_open_items_of_the_prior_phases(tiny_phase):
    facts = phase_clauses(tiny_phase)
    kinds = {d.path: [c.kind for c in d.clauses] for d in facts.docs}
    assert kinds == {
        "pdfs/MX01/ARI_open.pdf": ["instalments"],  # carried over open: its PDF is in the earlier phase
        "pdfs/US01/ARC_1.pdf": ["rappel_offset"], "pdfs/US01/API_1.pdf": ["factored"],
        "pdfs/PT01/NOTICE_1.pdf": ["new_iban"], "pdfs/MX01/PF.pdf": [],
    }
    # the closed invoice of the earlier phase was not even read, the corrupt one is recorded and skipped
    assert [path for path, _ in facts.failures] == ["pdfs/US01/broken.pdf"]


def test_for_item_and_for_number_answer_with_the_clauses_of_the_document(tiny_phase):
    facts = phase_clauses(tiny_phase)
    assert [c.kind for c in facts.for_item("ARI-1")] == ["instalments"]
    assert [c.kind for c in facts.for_item("API-1")] == ["factored"]
    assert facts.for_item("ARI-2") == [] and facts.for_item("nope") == []
    assert [c.kind for c in facts.for_number("US01", "cm07-2300636".replace("-", "").upper())] == ["rappel_offset"]
    assert facts.has_pdf("ARI-1") and not facts.has_pdf("ARI-2")


def test_new_iban_notices_are_found_by_party(tiny_phase):
    facts = phase_clauses(tiny_phase)
    assert [(d.party_id, d.entity, c.value["iban"]) for d, c in facts.notices()] == [
        ("C5", "PT01", "PT08944053240930376394569")]
    assert facts.notices(party_id="C9") == []


def test_clauses_frame_has_one_parser_row_per_clause_with_json_value(tiny_phase):
    frame = clauses_frame(phase_clauses(tiny_phase))
    row = frame.filter(pl.col("clause") == "instalments").row(0, named=True)
    assert (row["docPath"], row["docKind"], row["entity"], row["documentNumber"], row["method"], row["model"]) == (
        "pdfs/MX01/ARI_open.pdf", "invoicePdf", "MX01", "A01-2207305", "parser", None)
    assert json.loads(row["clauseValue"])["amounts"] == [974853, 974854]
    assert sorted(frame["docKind"].unique().to_list()) == ["bankAccountNotice", "creditNotePdf", "invoicePdf"]
    assert json.loads(frame.filter(pl.col("clause") == "new_iban")["clauseValue"][0])["partyId"] == "C5"
    assert frame.height == 4  # the proforma and the broken file have no clause


def test_residue_counts_documents_with_a_hint_and_no_clause(tmp_path):
    root = tmp_path / "phase"
    pdf_folder(root, [("A/ok.pdf", "invoice", "1", "A", "C", "2023-01-01")], {"A/ok.pdf": "instalments_en"})
    facts = phase_clauses(SimpleNamespace(name="r", dir=root, prior=[], items=items([])))
    assert residue(facts) == {"invoice": {"read": 1, "with_clause": 1, "hinted_unextracted": 0, "failed": 0}}


# --- cache of the parsed files -----------------------------------------------------------------------------------


@pytest.fixture
def parsed(monkeypatch):
    """The paths the parser really opened; the rest came from the cache."""
    opened: list[str] = []
    real = pdfs._parse_chunk

    def chunk(jobs):
        opened.extend(Path(path).name for path, _ in jobs)
        return real(jobs)

    monkeypatch.setattr(pdfs, "_parse_chunk", chunk)
    return opened


@pytest.fixture
def jobs(tmp_path):
    """A document with a clause and a file that is not a PDF."""
    good = tmp_path / "good.pdf"
    shutil.copy(FIXTURES / "instalments_en.pdf", good)
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    return [(str(good), "2024-05-01"), (str(bad), None)]


def test_the_second_read_opens_no_file_and_gives_the_same_facts(jobs, parsed):
    first = pdfs._parse_all(jobs)
    assert sorted(parsed) == ["bad.pdf", "good.pdf"]
    parsed.clear()
    second = pdfs._parse_all(jobs)
    assert parsed == []
    assert second == first
    assert second[0][0], "the document has a clause"
    assert isinstance(second[1], str), "a file that does not read stays recorded as such"


def test_a_file_with_new_content_is_read_again(jobs, parsed):
    pdfs._parse_all(jobs)
    parsed.clear()
    shutil.copy(FIXTURES / "retention_en.pdf", jobs[0][0])
    pdfs._parse_all(jobs)
    assert parsed == ["good.pdf"]


def test_the_same_file_with_another_document_date_is_read_again(jobs, parsed):
    """The date decides the year of a date without one: the facts depend on it."""
    pdfs._parse_all(jobs)
    parsed.clear()
    pdfs._parse_all([(jobs[0][0], "2019-05-01"), jobs[1]])
    assert parsed == ["good.pdf"]


def test_another_version_of_the_parser_reads_everything_again(jobs, parsed, monkeypatch):
    pdfs._parse_all(jobs)
    parsed.clear()
    monkeypatch.setattr(pdfs, "_cache_version", lambda: "another")
    pdfs._parse_all(jobs)
    assert sorted(parsed) == ["bad.pdf", "good.pdf"]


def test_the_version_covers_the_modules_the_parser_uses_and_pypdf(monkeypatch, tmp_path):
    base = pdfs._cache_version()
    monkeypatch.setattr(pdfs, "version", lambda name: "0.0.0")
    assert pdfs._cache_version() != base
    monkeypatch.undo()
    real_read = Path.read_bytes

    def changed(path):
        return b"changed" if path.name == "advices.py" else real_read(path)

    monkeypatch.setattr(Path, "read_bytes", changed)
    assert pdfs._cache_version() != base


def test_a_broken_cache_is_an_empty_one(jobs, parsed):
    first = pdfs._parse_all(jobs)
    pdfs._cache_file().write_bytes(b"not a pickle")
    parsed.clear()
    assert pdfs._parse_all(jobs) == first
    assert sorted(parsed) == ["bad.pdf", "good.pdf"]


def test_a_run_that_finds_everything_does_not_rewrite_the_cache(jobs):
    pdfs._parse_all(jobs)
    written = pdfs._cache_file().stat().st_mtime_ns
    pdfs._parse_all(jobs)
    assert pdfs._cache_file().stat().st_mtime_ns == written


def test_a_new_file_keeps_what_the_cache_already_had(jobs, parsed):
    pdfs._parse_all(jobs[:1])
    pdfs._parse_all(jobs[1:])
    parsed.clear()
    pdfs._parse_all(jobs)
    assert parsed == []


def test_an_unexpected_failure_is_reported_but_not_remembered(jobs, parsed, monkeypatch):
    real = pdfs._parse_one

    def broken(path, doc_date):
        raise MemoryError("out of memory")

    monkeypatch.setattr(pdfs, "_parse_one", broken)
    assert isinstance(pdfs._parse_all(jobs)[0], str)
    monkeypatch.setattr(pdfs, "_parse_one", real)
    parsed.clear()
    assert pdfs._parse_all(jobs)[0][0], "it reads once the failure is gone"
    assert "good.pdf" in parsed


def test_a_file_that_is_missing_is_a_failure_and_not_an_error(tmp_path):
    results = pdfs._parse_all([(str(tmp_path / "gone.pdf"), None)])
    assert isinstance(results[0], str)
