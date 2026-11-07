from __future__ import annotations

from types import SimpleNamespace

import polars as pl

from closebooks.documents.advices import phase_advices
from closebooks.load import load_table
from closebooks.paths import phase_dir
from closebooks.rules import advices

HEADER = "document,doc_date,gross,discount_or_deduction,reason,paid,your_order\n"


def golden_pairs(segments=None):
    g = load_table(phase_dir("sample") / "golden_allocations.csv.gz").filter(pl.col("item_id").is_not_null())
    if segments:
        g = g.filter(pl.col("segment").is_in(segments))
    return set(zip(g["bank_txn_id"], g["item_id"], strict=True))


def test_sample_pairs_are_precise_and_cover_what_advices_cover(sample):
    proposals = advices.propose(sample)
    mine = {(t, i) for t, p in proposals.items() for i, _ in p.lines}
    assert len(mine & golden_pairs()) / len(mine) > 0.995
    covered = golden_pairs(["ar_1toN_remittance", "ar_short_dispute", "ar_1to1_remittance"])
    # The sample only has the advices received in June: cash of late June whose advice came in July has none here.
    assert len(mine & covered) > 5000


def make_phase(tmp_path, files, txns, items):
    """files {name: (payer, received, text)}; txns [(id, cents, date, text)]; items [(id, type, number, cents)]."""
    folder = tmp_path / "remittance_advices" / "ES01"
    folder.mkdir(parents=True)
    index = ["file,entity,payer_name,received_date,format"]
    for name, (payer, received, text) in files.items():
        (folder / name).write_text(text)
        index.append(f"ES01/{name},ES01,{payer},{received},csv")
    (tmp_path / "remittance_advices" / "index.csv").write_text("\n".join(index) + "\n")
    frame = pl.DataFrame({
        "bank_txn_id": [t[0] for t in txns], "entity": ["ES01"] * len(txns), "amount_cents": [t[1] for t in txns],
        "booking_date": [t[2] for t in txns], "text": [t[3] for t in txns], "currency": ["EUR"] * len(txns),
        "orig_cents": [None] * len(txns), "orig_currency": [None] * len(txns), "ref1": [None] * len(txns),
        "ref2": [None] * len(txns), "end_to_end_id": [None] * len(txns), "remittance_info": [None] * len(txns),
        "counterparty_name": [None] * len(txns),
    }, schema_overrides={"orig_cents": pl.Int64, "orig_currency": pl.String, "ref1": pl.String, "ref2": pl.String,
                         "end_to_end_id": pl.String, "remittance_info": pl.String, "counterparty_name": pl.String})
    table = pl.DataFrame({
        "item_id": [i[0] for i in items], "item_type": [i[1] for i in items], "entity": ["ES01"] * len(items),
        "document_number": [i[2] for i in items], "total_cents": [i[3] for i in items],
        "currency": ["EUR"] * len(items), "issue_date": ["2024-01-30"] * len(items),
        "customer_po": [None] * len(items)}, schema_overrides={"customer_po": pl.String})
    return SimpleNamespace(dir=tmp_path, txns=frame, items=table)


ITEMS = [("ARI-1", "ARI", "FV24-0401885", 65891), ("ARI-2", "ARI", "FV24-0401886", 100000),
         ("ARC-1", "ARC", "AB24-0400077", 32945)]
ADVICE = ("payment_ref;240308783211;payment_date;2024-03-08;currency;EUR\n"
          "document;doc_date;gross;discount_or_deduction;reason;paid;your_order\n"
          "FV24-0401885;30/01/2024;658.91;;;658.91;\nAB24-0400077;13/02/2024;-329.45;;;-329.45;\n"
          "TOTAL;;;;;329.46;\n")


def test_reference_in_the_bank_text_settles_invoice_and_credit_note_with_the_cash_of_each_line(tmp_path):
    phase = make_phase(tmp_path, {"RA_a.csv": ("Arenal", "2024-03-12", ADVICE)},
                       [("BT-1", 32946, "2024-03-11", "TRANSFERENCIA ARENAL AVISO 240308783211")], ITEMS)
    proposal = advices.propose(phase)["BT-1"]
    assert proposal.rule == "ADVICE-CSV" and proposal.confidence == 1.0
    assert proposal.lines == [("ARI-1", 65891), ("ARC-1", 32945)]  # the credit note is positive, like the golden
    assert proposal.sources == [{"kind": "remittanceAdvice", "ref": "remittance_advices/ES01/RA_a.csv",
                                 "label": "240308783211"}]


def test_a_stated_deduction_and_its_reason_travel_with_the_proposal(tmp_path):
    text = ADVICE.replace("FV24-0401885;30/01/2024;658.91;;;658.91",
                          "FV24-0401885;30/01/2024;658.91;-65.89;PRICE DIFF;593.02")
    text = text.replace("329.46", "263.57")
    phase = make_phase(tmp_path, {"RA_a.csv": ("Arenal", "2024-03-12", text)},
                       [("BT-1", 26357, "2024-03-11", "TRANSFERENCIA ARENAL AVISO 240308783211")], ITEMS)
    proposal = advices.propose(phase)["BT-1"]
    assert proposal.lines == [("ARI-1", 59302), ("ARC-1", 32945)]
    assert proposal.deductions == {"ARI-1": (-6589, "PRICE DIFF")}


def test_a_number_without_prefix_year_or_leading_zeros_finds_our_invoice(tmp_path):
    text = ADVICE.replace("FV24-0401885", "401885").replace("AB24-0400077", "400077")
    phase = make_phase(tmp_path, {"RA_a.csv": ("Arenal", "2024-03-12", text)},
                       [("BT-1", 32946, "2024-03-11", "AVISO 240308783211")], ITEMS)
    assert [i for i, _ in advices.propose(phase)["BT-1"].lines] == ["ARI-1", "ARC-1"]


def test_without_a_reference_the_payer_name_and_the_dates_pair_a_late_advice_with_its_cash(tmp_path):
    phase = make_phase(tmp_path, {"RA_a.csv": ("Arénal del Sur S.L.", "2024-03-12", ADVICE)},
                       [("BT-1", 32946, "2024-03-08", "TRANSFERENCIA ARENAL DEL SUR S.L. PAGO FACTURAS")], ITEMS)
    assert "BT-1" in advices.propose(phase)  # the accent in the advice is not in the bank text
    # The same cash booked a month before the advice reached us is somebody else's.
    early = make_phase(tmp_path / "early", {"RA_a.csv": ("Arenal del Sur S.L.", "2024-04-12", ADVICE)},
                       [("BT-1", 32946, "2024-03-08", "TRANSFERENCIA ARENAL DEL SUR S.L. PAGO FACTURAS")], ITEMS)
    assert advices.propose(early) == {}


def test_a_different_amount_is_never_paired_even_with_the_reference(tmp_path):
    phase = make_phase(tmp_path, {"RA_a.csv": ("Arenal", "2024-03-12", ADVICE)},
                       [("BT-1", 32947, "2024-03-11", "AVISO 240308783211")], ITEMS)
    assert advices.propose(phase) == {}


def test_two_bank_lines_for_one_advice_get_no_proposal_and_are_counted(tmp_path):
    phase = make_phase(tmp_path, {"RA_a.csv": ("Arenal", "2024-03-12", ADVICE)},
                       [("BT-1", 32946, "2024-03-10", "AVISO 240308783211"),
                        ("BT-2", 32946, "2024-03-11", "AVISO 240308783211")], ITEMS)
    proposals, stats = advices.match(phase)
    assert proposals == {} and stats["advice fitting several bank lines"] == 2


def test_two_advices_for_one_bank_line_get_no_proposal_and_are_counted(tmp_path):
    other = ADVICE.replace("FV24-0401885", "FV24-0401886").replace("658.91", "1000.00").replace("329.46", "670.55")
    phase = make_phase(tmp_path, {"RA_a.csv": ("Arenal", "2024-03-12", ADVICE),
                                  "RA_b.csv": ("Arenal", "2024-03-12", other.replace("670.55", "329.46"))},
                       [("BT-1", 32946, "2024-03-11", "AVISO 240308783211")], ITEMS)
    proposals, stats = advices.match(phase)
    assert proposals == {} and stats["bank line with several advices"] == 1


def test_an_advice_that_does_not_close_still_pairs_but_does_not_claim_the_cash_of_each_line(tmp_path):
    # Lines of 658.91 and -329.45 print no shortfall, the e-mail total says 320.00: the paid amounts are unknown.
    text = ADVICE.replace("329.46", "320.00")
    phase = make_phase(tmp_path, {"RA_a.csv": ("Arenal", "2024-03-12", text)},
                       [("BT-1", 32000, "2024-03-11", "AVISO 240308783211")], ITEMS)
    proposal = advices.propose(phase)["BT-1"]
    assert proposal.lines == [("ARI-1", None), ("ARC-1", None)] and proposal.confidence < 0.9


def test_an_advice_short_of_its_lines_keeps_them_in_the_printed_order_and_says_so(tmp_path):
    text = ("Subject: Payment advice 240308783211\nDate: Mon, 11 Mar 2024 09:00:00 +0100\n\n"
            "We have sent a payment of 1,329.46 EUR on 03/11/2024 covering:\n\n"
            "  FV24-0401886  20/02/24  1,000.00\n  FV24-0401885  30/01/24  658.91\n")
    phase = make_phase(tmp_path, {"RA_a.txt": ("Arenal", "2024-03-12", text)},
                       [("BT-1", 132946, "2024-03-11", "AVISO 240308783211")], ITEMS)
    proposal = advices.propose(phase)["BT-1"]
    assert [i for i, _ in proposal.lines] == ["ARI-2", "ARI-1"]
    assert proposal.by_cash and proposal.in_listed_order
    assert proposal.sources[0]["ref"] == "remittance_advices/ES01/RA_a.txt"


def test_an_advice_that_closes_says_how_much_goes_to_each_line_so_no_order_applies(tmp_path):
    phase = make_phase(tmp_path, {"RA_a.csv": ("Arenal", "2024-03-12", ADVICE)},
                       [("BT-1", 32946, "2024-03-11", "AVISO 240308783211")], ITEMS)
    assert not advices.propose(phase)["BT-1"].in_listed_order


def test_cash_booked_after_the_advice_arrived_is_not_its_cash(tmp_path):
    phase = make_phase(tmp_path, {"RA_a.csv": ("Arenal del Sur S.L.", "2024-03-08", ADVICE)},
                       [("BT-1", 32946, "2024-03-20", "TRANSFERENCIA ARENAL DEL SUR S.L. PAGO FACTURAS")], ITEMS)
    assert advices.propose(phase) == {}


def test_a_line_whose_gross_is_not_the_total_of_the_item_with_that_number_is_not_mapped(tmp_path):
    items = [("ARI-1", "ARI", "FV24-0401885", 65892), ("ARC-1", "ARC", "AB24-0400077", 32945)]
    phase = make_phase(tmp_path, {"RA_a.csv": ("Arenal", "2024-03-12", ADVICE)},
                       [("BT-1", 32946, "2024-03-11", "AVISO 240308783211")], items)
    proposal = advices.propose(phase)["BT-1"]
    assert proposal.lines == [("ARC-1", 32945)] and proposal.confidence < 0.9


def test_numbers_with_a_series_between_prefix_and_sequence_are_found_without_them(tmp_path):
    # BR01 prints NF0123019416 (prefix, series 01, year 23, sequence); IT01 prints FT23-01-30385.
    items = [("ARI-1", "ARI", "NF0123019416", 65891), ("ARI-2", "ARI", "FT23-01-30385", 100000)]
    text = ("payment_ref;7700000001;payment_date;2024-03-08;currency;EUR\n"
            "document;doc_date;gross;discount_or_deduction;reason;paid;your_order\n"
            "19416;30/01/2024;658.91;;;658.91;\n30385;30/01/2024;1000.00;;;1000.00;\nTOTAL;;;;;1658.91;\n")
    phase = make_phase(tmp_path, {"RA_a.csv": ("Arenal", "2024-03-12", text)},
                       [("BT-1", 165891, "2024-03-11", "AVISO 7700000001 REMESA PAGOS")], items)
    assert [i for i, _ in advices.propose(phase)["BT-1"].lines] == ["ARI-1", "ARI-2"]


def test_a_reference_cut_by_the_bank_still_pairs_when_the_date_fits_but_not_otherwise(tmp_path):
    cut = "TRANSF. EN DIV. | DCIIHDXX -ARENAL | 24030878"  # N43 keeps 38 characters of 240308783211
    phase = make_phase(tmp_path, {"RA_a.csv": ("Industrias Zeta", "2024-03-12", ADVICE)},
                       [("BT-1", 32946, "2024-03-11", cut)], ITEMS)
    assert "BT-1" in advices.propose(phase)
    late = make_phase(tmp_path / "late", {"RA_a.csv": ("Industrias Zeta", "2024-03-12", ADVICE)},
                      [("BT-1", 32946, "2024-04-30", cut)], ITEMS)
    assert advices.propose(late) == {}


def with_prior_advices(phase, tmp_path, files, start):
    """The phase starts on `start`; `files` are the advices of the previous phase, like make_phase's."""
    older = make_phase(tmp_path / "prior", files, [], [])
    phase.prior, phase.start = [older.dir], start
    return phase


def test_an_advice_received_the_day_before_the_phase_in_the_previous_one_pairs_with_the_first_day_cash(tmp_path):
    phase = make_phase(tmp_path, {}, [("BT-1", 32946, "2024-03-11", "TRANSFERENCIA ARENAL DEL SUR S.L. PAGO FACTURAS")],
                       ITEMS)
    with_prior_advices(phase, tmp_path, {"RA_a.csv": ("Arenal del Sur S.L.", "2024-03-10", ADVICE)}, "2024-03-11")
    proposal = advices.propose(phase)["BT-1"]
    assert [i for i, _ in proposal.lines] == ["ARI-1", "ARC-1"]
    assert proposal.sources[0]["ref"] == "remittance_advices/ES01/RA_a.csv"


def test_previous_phase_advices_outside_the_window_are_not_even_parsed(tmp_path):
    # An unreadable file only shows up as a failure if somebody parsed it.
    phase = make_phase(tmp_path, {}, [("BT-1", 32946, "2024-03-11", "AVISO 240308783211")], ITEMS)
    with_prior_advices(phase, tmp_path, {"RA_in.csv": ("Arenal", "2024-03-08", ADVICE),
                                         "RA_out.csv": ("Arenal", "2024-03-07", "not an advice")}, "2024-03-11")
    batch = phase_advices(phase)
    assert [a.path for a in batch.advices] == ["remittance_advices/ES01/RA_in.csv"] and batch.failures == []


def test_an_advice_received_outside_the_window_before_the_phase_is_not_its_cash_by_name(tmp_path):
    phase = make_phase(tmp_path, {}, [("BT-1", 32946, "2024-03-11", "TRANSFERENCIA ARENAL DEL SUR S.L. PAGO FACTURAS")],
                       ITEMS)
    with_prior_advices(phase, tmp_path, {"RA_a.csv": ("Arenal del Sur S.L.", "2024-03-07", ADVICE)}, "2024-03-11")
    assert advices.propose(phase) == {}
