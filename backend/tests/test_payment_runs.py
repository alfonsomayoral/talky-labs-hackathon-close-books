from __future__ import annotations

from types import SimpleNamespace

import polars as pl

from closebooks.load import load_table
from closebooks.paths import phase_dir
from closebooks.rules import payment_runs


def golden_pairs(segments=None):
    g = load_table(phase_dir("sample") / "golden_allocations.csv.gz").filter(pl.col("item_id").is_not_null())
    if segments:
        g = g.filter(pl.col("segment").is_in(segments))
    return set(zip(g["bank_txn_id"], g["item_id"], strict=True))


def proposed_pairs(proposals):
    return {(t, i) for t, p in proposals.items() for i, _ in p.lines}


def test_debit_citing_a_transfer_settles_exactly_the_documents_of_that_transfer(sample):
    # BT with end_to_end_id PR010025062613-0074, "FRAS 2025-0066 2025-0070": two invoices, nothing from other suppliers.
    txn = sample.txns.filter(pl.col("end_to_end_id") == "PR010025062613-0074").row(0, named=True)
    proposal = payment_runs.propose(sample)[txn["bank_txn_id"]]
    assert proposal.rule == "FILE-PAYMENT-RUN"
    expected = {i for t, i in golden_pairs() if t == txn["bank_txn_id"]}
    assert {i for i, _ in proposal.lines} == expected
    assert len(expected) == 2


def test_proposed_pairs_are_precise_and_cover_paid_files(sample):
    proposals = {t: p for t, p in payment_runs.propose(sample).items()}
    mine, gold = proposed_pairs(proposals), golden_pairs()
    assert len(mine & gold) / len(mine) > 0.995
    # Sample only has the files of June: payments of May files cannot be resolved here (TRAIN measures the rest).
    assert len(mine & gold) > 3000


def _phase_with_a_run(tmp_path, txn_text, amount_cents):
    folder = tmp_path / "payment_runs"
    folder.mkdir()
    (folder / "ES01_202505_1.csv").write_text(
        "run_id,run_type,execution_date,debtor_account_id,end_to_end_id,beneficiary,beneficiary_iban,currency,"
        "transfer_amount,document_number,document_type,document_amount,remittance_info\n"
        "PR010125052693,transfers,2025-05-26,ES01-PENA-EUR,PR010125052693-0302,ROTULACION TECH S.R.L.,,EUR,"
        "13681.40,F-1,INVOICE,13681.40,FRA F-1\n")
    items = pl.DataFrame({
        "item_id": ["API-2025-0000001"], "item_type": ["API"], "entity": ["ES01"], "party_id": ["SES01000001"],
        "party_name": ["ROTULACION TECH S.R.L."], "document_number": ["F-1"], "total_cents": [1368140],
        "open_cents": [1368140],
        "due_date": ["2025-05-26"]})
    txns = pl.DataFrame({
        "bank_txn_id": ["BT-1"], "account_id": ["ES01-PENA-EUR"], "booking_date": ["2025-05-26"],
        "amount_cents": [amount_cents],
        "orig_cents": [None], "orig_currency": [None],
        "text": [txn_text], "ref1": [None], "ref2": [None], "end_to_end_id": [None], "remittance_info": [None],
    }, schema_overrides={"orig_cents": pl.Int64, "orig_currency": pl.String, "ref1": pl.String, "ref2": pl.String,
                         "end_to_end_id": pl.String, "remittance_info": pl.String})
    return SimpleNamespace(dir=tmp_path, items=items, txns=txns)


def test_returned_transfer_is_a_reversal_of_the_documents_of_that_transfer(tmp_path):
    phase = _phase_with_a_run(tmp_path, "DEVOLUCION TRANSFERENCIA MD07 | ROTULACION TECH S.R.L. | PR010125052693-0302",
                              1368140)
    proposal = payment_runs.propose(phase)["BT-1"]
    assert proposal.returned
    assert proposal.rule == "FILE-PAYMENT-RETURN"
    assert proposal.lines == [("API-2025-0000001", 1368140)]


def _rejected(tmp_path, text, booked="2025-05-29"):
    phase = _phase_with_a_run(tmp_path, text, 1368140)
    phase.txns = phase.txns.with_columns(pl.lit(booked).alias("booking_date"))
    return payment_runs.propose(phase)


def test_rejected_transfer_with_no_reference_is_found_by_its_reason_code_amount_and_beneficiary(tmp_path):
    # BT-2025-0027691: the bank cites no run, only the reason and the supplier.
    proposal = _rejected(tmp_path, "DEVOLUCION TRANSFERENCIA MD07 | ROTULACION TECH S.R.L.")["BT-1"]
    assert proposal.rule == "FILE-PAYMENT-RETURN" and proposal.returned
    assert proposal.lines == [("API-2025-0000001", 1368140)]
    assert proposal.reference == "PR010125052693-0302"


def test_rejected_transfer_in_another_currency_comes_back_for_what_the_account_paid(tmp_path):
    # BT-2025-0074863: -53733.48 EUR for a transfer of 58064.93 USD; it returns as +53733.48 EUR, with nothing else.
    phase = _phase_with_a_run(tmp_path, "PR010125052693-0302", -1200000)
    back = phase.txns.with_columns(pl.lit("BT-2").alias("bank_txn_id"), pl.lit("2025-05-29").alias("booking_date"),
                                   pl.lit(1200000, pl.Int64).alias("amount_cents"),
                                   pl.lit("DEVOLUCION TRANSFERENCIA AC01 | ROTULACION TECH S.R.L.").alias("text"))
    phase.txns = pl.concat([phase.txns.with_columns(pl.lit(1368140, pl.Int64).alias("orig_cents"),
                                                    pl.lit("USD").alias("orig_currency")),
                            back.with_columns(pl.col("orig_cents").cast(pl.Int64))], how="vertical_relaxed")
    assert payment_runs.propose(phase)["BT-2"].lines == [("API-2025-0000001", 1368140)]


def test_credit_of_that_amount_and_supplier_with_no_reason_code_is_not_a_rejection(tmp_path):
    assert _rejected(tmp_path, "REEMBOLSO PAGO DOBLE | ROTULACION TECH S.R.L.") == {}


def test_rejection_of_another_supplier_is_not_this_transfer(tmp_path):
    assert _rejected(tmp_path, "DEVOLUCION TRANSFERENCIA MD07 | OTRO PROVEEDOR S.L.") == {}


def test_rejection_before_the_transfer_was_made_is_not_this_transfer(tmp_path):
    assert _rejected(tmp_path, "DEVOLUCION TRANSFERENCIA MD07 | ROTULACION TECH S.R.L.", booked="2025-05-20") == {}


def test_debit_citing_a_run_we_do_not_have_stays_unresolved(tmp_path):
    phase = _phase_with_a_run(tmp_path, "PAGO CONFIRMING | REMESA CF010121062515 3 PROVEEDORES", -1368140)
    assert payment_runs.propose(phase) == {}


def test_same_supplier_and_number_in_two_entities_resolves_to_the_entity_that_pays(tmp_path):
    phase = _phase_with_a_run(tmp_path, "PR010125052693-0302", -1368140)
    other = phase.items.with_columns(pl.lit("API-2025-0000000").alias("item_id"), pl.lit("AAAA").alias("entity"))
    phase.items = pl.concat([other, phase.items])
    assert payment_runs.propose(phase)["BT-1"].lines == [("API-2025-0000001", 1368140)]


def test_document_listed_twice_in_a_transfer_is_one_line_with_the_sum(tmp_path):
    phase = _phase_with_a_run(tmp_path, "PR010125052693-0302", -1368140)
    file = tmp_path / "payment_runs" / "ES01_202505_1.csv"
    lines = file.read_text().splitlines()
    file.write_text("\n".join([lines[0], lines[1].replace("13681.40,FRA", "1.40,FRA"), lines[1]]) + "\n")
    assert payment_runs.propose(phase)["BT-1"].lines == [("API-2025-0000001", 1368280)]


def test_same_transfer_id_in_another_account_is_a_different_payment(tmp_path):
    # PR010021070874-0068 exists in MA01 and MX01: real collision in TRAIN.
    phase = _phase_with_a_run(tmp_path, "PR010125052693-0302", -1368140)
    other = tmp_path / "payment_runs" / "MX01_202505_1.csv"
    first = (tmp_path / "payment_runs" / "ES01_202505_1.csv").read_text().splitlines()
    other.write_text("\n".join([first[0], first[1].replace("ES01-PENA-EUR", "MX01-MEZQ-MXN").replace("F-1", "F-2")]))
    assert payment_runs.propose(phase)["BT-1"].lines == [("API-2025-0000001", 1368140)]


def _confirming_phase(tmp_path, booking_date, amount_cents):
    # One debit per maturity: a transfer falls due when its last document does (CF010021091055, TRAIN).
    folder = tmp_path / "payment_runs"
    folder.mkdir()
    header = ("run_id,run_type,execution_date,debtor_account_id,end_to_end_id,beneficiary,beneficiary_iban,currency,"
              "transfer_amount,document_number,document_type,document_amount,remittance_info\n")
    row = "CF010021091055,confirming,2021-09-10,ES01-RIBA-EUR,CF010021091055-{e},{b},,EUR,{t},{n},INVOICE,{d},x\n"
    (folder / "ES01_202109_0.csv").write_text(
        header
        + row.format(e="0045", b="A SL", t="151.00", n="A-1", d="100.00")
        + row.format(e="0045", b="A SL", t="151.00", n="A-2", d="51.00")
        + row.format(e="0056", b="B SL", t="40.00", n="B-1", d="40.00")
        + row.format(e="0058", b="C SL", t="29.00", n="C-1", d="29.00"))
    items = pl.DataFrame({
        "item_id": ["API-1", "API-2", "API-3", "API-4"], "item_type": ["API"] * 4, "entity": ["ES01"] * 4,
        "party_id": ["SA", "SA", "SB", "SC"], "party_name": ["A SL", "A SL", "B SL", "C SL"],
        "document_number": ["A-1", "A-2", "B-1", "C-1"], "total_cents": [10000, 5100, 4000, 2900],
        "open_cents": [10000, 5100, 4000, 2900],
        "due_date": ["2021-08-18", "2021-09-07", "2021-09-07", "2021-09-20"]})
    txns = pl.DataFrame({
        "bank_txn_id": ["BT-1"], "account_id": ["ES01-RIBA-EUR"], "booking_date": [booking_date],
        "amount_cents": [amount_cents], "orig_cents": [None], "orig_currency": [None],
        "text": ["PAGO CONFIRMING | REMESA CF010021091055 2 PROVEEDORES"], "ref1": [None], "ref2": [None],
        "end_to_end_id": [None], "remittance_info": [None],
    }, schema_overrides={"orig_cents": pl.Int64, "orig_currency": pl.String, "ref1": pl.String, "ref2": pl.String,
                         "end_to_end_id": pl.String, "remittance_info": pl.String})
    return SimpleNamespace(dir=tmp_path, items=items, txns=txns)


def test_confirming_debit_settles_the_transfers_falling_due_that_day(tmp_path):
    phase = _confirming_phase(tmp_path, "2021-09-07", -19100)
    assert {i for i, _ in payment_runs.propose(phase)["BT-1"].lines} == {"API-1", "API-2", "API-3"}


def test_confirming_debit_booked_after_a_weekend_still_finds_its_maturity(tmp_path):
    phase = _confirming_phase(tmp_path, "2021-09-09", -19100)
    assert {i for i, _ in payment_runs.propose(phase)["BT-1"].lines} == {"API-1", "API-2", "API-3"}


def test_confirming_debit_whose_amount_matches_no_maturity_is_not_guessed(tmp_path):
    phase = _confirming_phase(tmp_path, "2021-09-07", -19101)
    assert payment_runs.propose(phase) == {}


def _with_another_transfer_due_that_day(phase, tmp_path, cents_text, cents):
    """A transfer of the same maturity that this debit does not pay: it goes out on its own, weeks later."""
    with (tmp_path / "payment_runs" / "ES01_202109_0.csv").open("a") as file:
        file.write(f"CF010021091055,confirming,2021-09-10,ES01-RIBA-EUR,CF010021091055-0060,D SL,,EUR,{cents_text},D-1,"
                   f"INVOICE,{cents_text},x\n")
    extra = {"item_id": "API-5", "item_type": "API", "entity": "ES01", "party_id": "SD", "party_name": "D SL",
             "document_number": "D-1", "total_cents": cents, "open_cents": cents, "due_date": "2021-09-07"}
    phase.items = pl.concat([phase.items, pl.DataFrame([extra])], how="vertical_relaxed")
    return phase


def test_confirming_debit_for_the_suppliers_it_says_leaves_out_the_other_of_that_maturity(tmp_path):
    # BT-2025-0000563: "8 PROVEEDORES" of a maturity with 9 transfers; the ninth is paid alone on 01-13.
    debit = _confirming_phase(tmp_path, "2021-09-07", -19100)
    phase = _with_another_transfer_due_that_day(debit, tmp_path, "12.00", 1200)
    assert {i for i, _ in payment_runs.propose(phase)["BT-1"].lines} == {"API-1", "API-2", "API-3"}


def test_confirming_debit_that_two_sets_of_suppliers_explain_is_not_guessed(tmp_path):
    debit = _confirming_phase(tmp_path, "2021-09-07", -19100)
    phase = _with_another_transfer_due_that_day(debit, tmp_path, "40.00", 4000)
    assert payment_runs.propose(phase) == {}


def test_partial_payment_to_a_factor_finds_the_invoice_in_the_entity_that_pays(tmp_path):
    phase = _phase_with_a_run(tmp_path, "PR010125052693-0302", -9582)
    file = tmp_path / "payment_runs" / "ES01_202505_1.csv"
    lines = file.read_text().splitlines()
    file.write_text("\n".join([lines[0], lines[1].replace("ROTULACION TECH S.R.L.", "CREDIFACIL EFC")
                               .replace("13681.40", "95.82")]) + "\n")
    copy = phase.items.with_columns
    phase.items = pl.concat([copy(pl.lit("ES01").alias("entity"), pl.lit("API-A").alias("item_id")),
                             copy(pl.lit("FR01").alias("entity"), pl.lit("API-B").alias("item_id"))])
    assert payment_runs.propose(phase)["BT-1"].lines == [("API-A", 9582)]


def test_monday_debit_collects_what_fell_due_over_the_weekend(tmp_path):
    # CF020022091286: debit on Monday 2022-09-19 clears transfers due on the 17th and the 18th.
    phase = _confirming_phase(tmp_path, "2021-09-08", -22000)
    earlier = pl.when(pl.col("item_id") == "API-4").then(pl.lit("2021-09-06")).otherwise(pl.col("due_date"))
    phase.items = phase.items.with_columns(earlier.alias("due_date"))
    assert {i for i, _ in payment_runs.propose(phase)["BT-1"].lines} == {"API-1", "API-2", "API-3", "API-4"}


def test_confirming_debit_paid_late_is_found_by_exact_amount_when_it_cites_one_supplier(tmp_path):
    # CF020021071266: "1 PROVEEDORES" booked on 09-29 for a transfer due on 07-08.
    phase = _confirming_phase(tmp_path, "2021-11-20", -2900)
    phase.txns = phase.txns.with_columns(pl.lit("PAGO CONFIRMING | REMESA CF010021091055 1 PROVEEDORES").alias("text"))
    assert {i for i, _ in payment_runs.propose(phase)["BT-1"].lines} == {"API-4"}


def test_aggregated_debit_citing_the_number_of_transfers_clears_the_whole_run_even_if_the_sum_differs(tmp_path):
    # PR010321070839: "BULK PAYMENT ... 341 TRANSFERS"; the file's amounts are in the document currency.
    phase = _confirming_phase(tmp_path, "2021-09-20", -99999)
    file = tmp_path / "payment_runs" / "ES01_202109_0.csv"
    file.write_text(file.read_text().replace(",confirming,", ",aggregated,"))
    phase.txns = phase.txns.with_columns(pl.lit("BULK PAYMENT CF010021091055 3 TRANSFERS").alias("text"))
    assert len(payment_runs.propose(phase)["BT-1"].lines) == 4


def test_aggregated_debit_with_another_count_and_sum_is_not_guessed(tmp_path):
    phase = _confirming_phase(tmp_path, "2021-09-20", -99999)
    file = tmp_path / "payment_runs" / "ES01_202109_0.csv"
    file.write_text(file.read_text().replace(",confirming,", ",aggregated,"))
    phase.txns = phase.txns.with_columns(pl.lit("BULK PAYMENT CF010021091055 7 TRANSFERS").alias("text"))
    assert payment_runs.propose(phase) == {}


def _factored(tmp_path, totals_opens):
    phase = _phase_with_a_run(tmp_path, "PR010125052693-0302", -9582)
    file = tmp_path / "payment_runs" / "ES01_202505_1.csv"
    lines = file.read_text().splitlines()
    file.write_text("\n".join([lines[0], lines[1].replace("ROTULACION TECH S.R.L.", "CREDIFACIL EFC")
                               .replace("13681.40", "95.82")]) + "\n")
    base = phase.items
    phase.items = pl.concat([base.with_columns(pl.lit(f"API-{i}").alias("item_id"), pl.lit("ES01").alias("entity"),
                                               pl.lit(t).alias("total_cents"), pl.lit(o).alias("open_cents"))
                             for i, (t, o) in enumerate(totals_opens)])
    return phase


def test_item_closed_in_an_earlier_phase_does_not_hide_the_open_one_with_the_same_number(tmp_path):
    phase = _factored(tmp_path, [(50000, 0), (45000, 45000)])
    assert payment_runs.propose(phase)["BT-1"].lines == [("API-1", 9582)]


def test_of_two_open_items_with_the_same_number_the_one_whose_balance_is_paid_wins(tmp_path):
    phase = _factored(tmp_path, [(50000, 9582), (45000, 45000)])
    assert payment_runs.propose(phase)["BT-1"].lines == [("API-0", 9582)]


def test_two_open_items_with_the_same_number_and_no_other_evidence_are_not_guessed(tmp_path):
    phase = _factored(tmp_path, [(50000, 50000), (45000, 45000)])
    assert payment_runs.propose(phase) == {}
