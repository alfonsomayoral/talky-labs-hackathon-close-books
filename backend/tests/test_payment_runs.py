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
        "due_date": ["2025-05-26"]})
    txns = pl.DataFrame({
        "bank_txn_id": ["BT-1"], "account_id": ["ES01-PENA-EUR"], "amount_cents": [amount_cents],
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
