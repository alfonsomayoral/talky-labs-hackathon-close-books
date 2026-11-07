from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest

from closebooks.categories import fallback, pure_category
from closebooks.load import load_table
from closebooks.model import Proposal
from closebooks.paths import phase_dir
from closebooks.resolve import resolve
from closebooks.rules import categories as rules
from closebooks.tools.learn_categories import learn


def txn(amount_cents, bank="PENA", code="", subcode="", text="", txn_id="BT-1"):
    return {"bank_txn_id": txn_id, "amount_cents": amount_cents, "currency": "EUR", "bank": bank, "bank_code": code,
            "bank_subcode": subcode, "text": text}


def codes(**combos):
    """combos: 'bank|code|subcode|direction' -> {label: count}."""
    return {tuple(key.split("|")): counts for key, counts in combos.items()}


TABLE = codes(**{
    "PENA|17|310|debit": {"BANK_FEES": 300},
    "RHEI|CAMT/ACCB/ZABA||credit": {"CASH_POOL": 60},
    "LORV|NSAL||debit": {"PAYROLL": 80},
    "LORV|NTRF||credit": {"ITEM": 900, "UNIDENTIFIED": 20},
    "LORV|NTRF||debit": {"ITEM": 900, "CUSTOMER_REFUND": 12, "INTERCOMPANY": 40},
    "WATT|NDDT||debit": {"ITEM": 5, "LEASING": 400},
    "WATT|NCHG||debit": {"BANK_FEES": 3},
})


def test_pure_code_claims_the_line_with_its_category_and_no_item():
    p = rules.claim(txn(-1210, "PENA", "17", "310", "COM. MANTENIMIENTO"), TABLE)
    assert (p.rule, p.category, p.lines) == ("CAT-CODE", "BANK_FEES", [])
    p = rules.claim(txn(90000, "RHEI", "CAMT/ACCB/ZABA", "", "CASH CONCENTRATION ES01 1"), TABLE)
    assert (p.rule, p.category) == ("CAT-CODE", "CASH_POOL")
    p = rules.claim(txn(-250000, "LORV", "NSAL", "", "NOMINA 06 25 -"), TABLE)
    assert (p.rule, p.category) == ("CAT-CODE", "PAYROLL")


def test_generic_code_is_not_claimed_by_code_nor_by_an_unrelated_text():
    assert rules.claim(txn(12345, "LORV", "NTRF", "", "TRANSFERENCIA DE ACME SL FV25-0001"), TABLE) is None


def test_a_combination_that_also_has_item_lines_is_never_claimed_by_code():
    # 5 of 405 are items: claiming it would block their rules, so the code alone does not decide.
    assert rules.claim(txn(-9900, "WATT", "NDDT", "", "ADEUDO RECIBO 123"), TABLE) is None


def test_a_pure_combination_with_too_little_history_is_not_claimed():
    assert rules.claim(txn(-100, "WATT", "NCHG", "", "COMISION MANTENIMIENTO"), TABLE) is None


def test_direction_is_part_of_the_key():
    assert rules.claim(txn(5000, "PENA", "17", "310", "X"), TABLE) is None


def test_unknown_combination_falls_to_text_keywords():
    p = rules.claim(txn(-100, "NEWB", "ZZ", "9", "ANULACION OPERACION INDEBIDA N 1234 COMISION"), TABLE)
    assert (p.rule, p.category) == ("CAT-TEXT", "BANK_REVERSAL")
    p = rules.claim(txn(-100, "NEWB", "ZZ", "9", "ADEUDO MENSUAL DE TARJETA ************1234"), TABLE)
    assert (p.rule, p.category) == ("CAT-TEXT", "CARD_EXPENSES")


def test_the_wrong_booking_of_a_bank_reversal_is_a_bare_generic_word_and_nothing_longer():
    for text in ("ABONO", "SEG. SOCIAL COTIZ.", "TRANSFERENCIA RECIBIDA"):
        assert rules.claim(txn(7000, "NEWB", "ZZ", "9", text), {}).category == "BANK_REVERSAL"
    assert rules.claim(txn(7000, "NEWB", "ZZ", "9", "ABONO FACTURA FV25-0001"), {}) is None


def test_intragroup_loan_texts_are_intercompany_not_a_customer_refund():
    assert rules.claim(txn(-700000, text="VIR SEPA EMIS /A /MOTIF DEVOLUCION PRESTAMO IC VALTERMIA IN /REF"),
                       {}).category == "INTERCOMPANY"
    assert rules.claim(txn(700000, text="BONIFICO DA CAUSALE PRESTAMO INTRAGRUPO VALTERMIA"),
                       {}).category == "INTERCOMPANY"


def test_interest_category_depends_on_direction():
    assert rules.claim(txn(900, text="LIQUIDACION INTERESES 2T25"), {}).category == "INTEREST_INCOME"
    assert rules.claim(txn(-900, text="LIQUIDACION INTERESES 2T25"), {}).category == "INTEREST_EXPENSE"


def test_proforma_payment_is_a_customer_advance_but_an_invoice_payment_is_not():
    assert rules.claim(txn(5000, text="SEPA-UEBERWEISUNG EREF+NOTPROVIDED SVWZ+PROFORMA PF25-0042"), {}).category == (
        "CUSTOMER_ADVANCE")
    assert rules.claim(txn(5000, text="SEPA-UEBERWEISUNG EREF+NOTPROVIDED SVWZ+INVOICE FV25-0042"), {}) is None


def test_duplicate_payment_refund_text_depends_on_who_refunds():
    assert rules.claim(txn(-5000, text="TRANSFERENCIA A BEATRIZ BRAVO | DEVOLUCION PAGO DUPLICADO FV24-1"),
                       {}).category == "CUSTOMER_REFUND"
    assert rules.claim(txn(5000, text="SEPA-UEBERWEISUNG EREF+NOTPROVIDED SVWZ+ABONO PAGO DOBLE"),
                       {}).category == "SUPPLIER_REFUND"


def test_refund_of_a_credit_note_cites_the_invoice_and_is_left_to_the_item_rules():
    assert rules.claim(txn(5000, text="TT IN SOFTWARE GLOBAL CO., LTD. REEMBOLSO FRA 2021-0143"), {}) is None


def test_unidentified_by_code_carries_its_exception():
    table = codes(**{"MONC|02|778|credit": {"UNIDENTIFIED": 500}})
    p = rules.claim(txn(10000, "MONC", "02", "778", "INGRESO EFECTIVO OFICINA 12"), table)
    assert (p.rule, p.category) == ("CAT-CODE", "UNIDENTIFIED")


def test_resolve_emits_a_category_row_for_a_category_proposal():
    items = pl.DataFrame({"item_id": ["ARI-1"], "open_cents": [1000], "total_cents": [1000], "currency": ["EUR"],
                          "party_id": ["C1"], "payment_terms": ["T30"], "issue_date": ["2025-01-01"]})
    masters = {
        "payment_terms": pl.DataFrame({"code": ["T30"], "early_payment_discount_pct": [None], "discount_days": [None]},
                                      schema_overrides={"early_payment_discount_pct": pl.String,
                                                        "discount_days": pl.String}),
        "customers": pl.DataFrame({"customer_id": ["C1"], "country": ["ES"]}),
    }
    for amount, category, exception in ((-1000, "BANK_FEES", None), (1000, "UNIDENTIFIED", "UNIDENTIFIED")):
        t = pl.DataFrame({"bank_txn_id": ["BT-1"], "booking_date": ["2025-01-01"], "amount_cents": [amount],
                          "currency": ["EUR"], "bank": ["PENA"], "bank_code": ["17"], "bank_subcode": ["310"],
                          "text": ["X"], "orig_cents": [None], "orig_currency": [None], "amount_eur_cents": [amount],
                          "entity": ["E1"], "counterparty_name": [None], "counterparty_account": [None],
                          "remittance_info": [None], "ref1": [None], "ref2": [None], "end_to_end_id": [None]},
                         schema_overrides={"orig_cents": pl.Int64, "orig_currency": pl.String,
                                           "counterparty_name": pl.String, "counterparty_account": pl.String,
                                           "remittance_info": pl.String, "ref1": pl.String, "ref2": pl.String,
                                           "end_to_end_id": pl.String})
        rows, _ = resolve(SimpleNamespace(items=items, txns=t, masters=masters),
                          {"BT-1": Proposal(rule="CAT-CODE", lines=[], category=category)})
        assert len(rows) == 1
        r = rows[0]
        assert (r.item_id, r.amount_cents, r.currency, r.category, r.exception, r.rule) == (
            None, None, None, category, exception, "CAT-CODE")


def test_fallback_for_a_debit_is_the_most_frequent_category_of_its_code_never_item():
    out = fallback(txn(-500, "LORV", "NTRF", "", "TRANSFERENCIA A ALGUIEN"), TABLE)
    assert (out.category, out.exception, out.rule) == ("INTERCOMPANY", "", "FALLBACK-CATEGORY")


def test_fallback_for_a_debit_in_an_unknown_combination_is_bank_fees():
    assert fallback(txn(-500, "NEWB", "ZZ", "9", "ALGO"), TABLE).category == "BANK_FEES"


def test_fallback_for_a_receipt_is_unidentified_even_when_its_code_has_other_categories():
    table = codes(**{"LORV|NTRF||credit": {"ITEM": 900, "CUSTOMER_ADVANCE": 200}})
    out = fallback(txn(500, "LORV", "NTRF", "", "TRANSFERENCIA DE ALGUIEN"), table)
    assert (out.category, out.exception, out.rule) == ("UNIDENTIFIED", "UNIDENTIFIED", "FALLBACK-UNIDENTIFIED")


def test_learn_counts_labels_by_code_and_direction_before_the_cut():
    txns = pl.DataFrame({
        "bank_txn_id": ["a", "b", "c", "d", "e"], "bank": ["PENA"] * 5, "bank_code": ["17", "17", "04", "04", "04"],
        "bank_subcode": ["310", "310", None, None, None], "booking_date": ["2024-05-01"] * 4 + ["2025-02-01"],
        "amount": ["-1.00", "-2.00", "10.00", "11.00", "12.00"]})
    golden = pl.DataFrame({
        "bank_txn_id": ["a", "b", "c", "d", "e"], "item_id": [None, None, "ARI-1", None, "ARI-2"],
        "category": ["BANK_FEES", "BANK_FEES", None, "UNIDENTIFIED", None]})
    got = {(r["bank_code"], r["bank_subcode"], r["direction"], r["label"]): r["count"]
           for r in learn(txns, golden, before="2025-01-01").iter_rows(named=True)}
    assert got == {("17", "310", "debit", "BANK_FEES"): 2, ("04", "", "credit", "ITEM"): 1,
                   ("04", "", "credit", "UNIDENTIFIED"): 1}


def test_claims_on_the_sample_are_precise_and_never_take_a_line_with_items(sample):
    golden = load_table(phase_dir("sample") / "golden_allocations.csv.gz").group_by("bank_txn_id").agg(
        pl.col("item_id").is_not_null().any().alias("has_item"), pl.col("category").drop_nulls().first())
    truth = {r["bank_txn_id"]: r for r in golden.iter_rows(named=True)}
    everything = rules.propose(sample)
    assert any(p.rule == "CAT-SUPPLIER-REFUND" for p in everything.values())
    claimed = {t: p for t, p in everything.items() if p.category}
    assert len(claimed) > 500
    right = sum(1 for t, p in claimed.items() if truth[t]["category"] == p.category)
    taken_items = sum(1 for t in claimed if truth[t]["has_item"])
    assert right / len(claimed) > 0.995
    assert taken_items / len(claimed) < 0.002


@pytest.mark.parametrize("code,sub,direction,label", [("17", "310", "debit", "BANK_FEES")])
def test_committed_table_knows_the_basic_codes(code, sub, direction, label):
    from closebooks.categories import load_codes

    assert load_codes()[("PENA", code, sub, direction)][label] > 1000


def refund_phase(note_overrides=None, **txn_overrides):
    """One credit note of 155.47 EUR of supplier SES01000001 in ES01, and one receipt of the same amount."""
    note = {"item_id": "APC-2025-0000001", "item_type": "APC", "entity": "ES01", "party_id": "SES01000001",
            "party_name": "FILTROS PENA S.L.", "document_number": "AB-INV0001441", "related_document": "INV0001441",
            "currency": "EUR", "total_cents": 15547, "issue_date": "2025-05-14", **(note_overrides or {})}
    receipt = {"bank_txn_id": "BT-1", "entity": "ES01", "currency": "EUR", "amount_cents": 15547,
               "booking_date": "2025-06-02", "text": "TRANSFERENCIA SEPA | 81734825-FILTROS PENA S.L. | ABONO",
               "ref1": None, "ref2": None, "end_to_end_id": None, "remittance_info": None, "counterparty_name": None,
               **txn_overrides}
    suppliers = pl.DataFrame({"supplier_id": ["SES01000001"], "name": ["FILTROS PENA S.L."]})
    return SimpleNamespace(items=pl.DataFrame([note]), txns=pl.DataFrame([receipt]), masters={"suppliers": suppliers})


def test_receipt_of_the_exact_amount_citing_the_credit_note_number_settles_it():
    phase = refund_phase(text="TRANSFERENCIA SEPA | 81734825-X | ABONO AB-INV0001441")
    p = rules.propose_supplier_refunds(phase)["BT-1"]
    assert (p.rule, p.lines, p.party_id, p.category) == ("CAT-SUPPLIER-REFUND", [("APC-2025-0000001", None)],
                                                          "SES01000001", None)


def test_the_invoice_a_credit_note_refers_to_is_also_a_number():
    phase = refund_phase(text="TRANSF. A SU FAVOR | 1-X | DEVOLUCION INV0001441")
    assert "BT-1" in rules.propose_supplier_refunds(phase)


def test_the_supplier_name_with_the_exact_amount_identifies_the_credit_note():
    assert "BT-1" in rules.propose_supplier_refunds(refund_phase())


def test_the_same_amount_without_number_or_name_is_not_a_refund():
    phase = refund_phase(text="SEPA-UEBERWEISUNG EREF+NOTPROVIDED SVWZ+PAYMENT")
    assert rules.propose_supplier_refunds(phase) == {}


def test_a_refund_needs_the_same_entity_currency_and_a_credit_note_already_issued():
    assert rules.propose_supplier_refunds(refund_phase(entity="ES02")) == {}
    assert rules.propose_supplier_refunds(refund_phase(currency="USD")) == {}
    assert rules.propose_supplier_refunds(refund_phase({"issue_date": "2025-06-30"})) == {}
    assert rules.propose_supplier_refunds(refund_phase(amount_cents=-15547)) == {}


def test_two_credit_notes_of_the_same_amount_and_supplier_are_not_guessed():
    phase = refund_phase()
    twin = phase.items.with_columns(
        pl.lit("APC-2025-0000002").alias("item_id"), pl.lit("AB-OTHER").alias("document_number"),
        pl.lit("OTHER").alias("related_document"))
    phase.items = pl.concat([phase.items, twin])
    assert rules.propose_supplier_refunds(phase) == {}


def test_a_credit_note_carried_over_without_a_name_is_found_through_the_supplier_master():
    phase = refund_phase({"party_name": None, "related_document": None})
    assert "BT-1" in rules.propose_supplier_refunds(phase)


def test_supplier_refunds_on_the_sample_are_precise(sample):
    golden = load_table(phase_dir("sample") / "golden_allocations.csv.gz").filter(pl.col("item_id").is_not_null())
    pairs = set(zip(golden["bank_txn_id"], golden["item_id"], strict=True))
    claimed = rules.propose_supplier_refunds(sample)
    assert len(claimed) > 50
    right = sum(1 for t, p in claimed.items() if (t, p.lines[0][0]) in pairs)
    assert right / len(claimed) > 0.995


def test_supplier_named_only_as_the_ordering_party_settles_its_credit_note():
    # BT-2025-0002445: "DEVOLUCION SALDO A FAVOR", and the supplier only in the counterparty.
    phase = refund_phase(text="SEPA-UEBERWEISUNG EREF+NOTPROVIDED SVWZ+DEVOLUCION SALDO A FAVOR",
                         counterparty_name="FILTROS PENA S.L.")
    assert rules.propose_supplier_refunds(phase)["BT-1"].lines == [("APC-2025-0000001", None)]


def test_supplier_written_without_its_accents_by_the_bank_settles_its_credit_note():
    # BT-2025-0002848: the bank prints LOGISTICA for Logística.
    phase = refund_phase({"party_name": "Logística Global S.L."},
                         text="TRANSFERENCIA SEPA | 3126-LOGISTICA GLOBAL S.L.")
    assert rules.propose_supplier_refunds(phase)["BT-1"].lines == [("APC-2025-0000001", None)]



OTHER_BANKS = codes(**{
    "OLD1|NCHG||debit": {"BANK_FEES": 8}, "OLD2|NCHG||debit": {"BANK_FEES": 8},
    "OLD1|NTRF||debit": {"ITEM": 100, "CUSTOMER_REFUND": 6, "INTERCOMPANY": 2},
    "OLD2|THIN||debit": {"INSURANCE": 3},
})


def test_a_bank_never_seen_takes_a_code_all_the_banks_agree_on_with_enough_lines_together():
    assert pure_category(OTHER_BANKS, txn(-100, bank="NEWB", code="NCHG")) == "BANK_FEES"


def test_a_bank_never_seen_gets_no_category_from_a_code_that_also_settles_items_or_is_rare():
    assert pure_category(OTHER_BANKS, txn(-100, bank="NEWB", code="NTRF")) is None
    assert pure_category(OTHER_BANKS, txn(-100, bank="NEWB", code="THIN")) is None


def test_a_known_bank_only_looks_at_its_own_history():
    assert pure_category(OTHER_BANKS, txn(-100, bank="OLD1", code="NCHG")) is None  # 8 lines of its own: too few
    assert fallback(txn(-100, bank="OLD2", code="NTRF"), OTHER_BANKS).category == "BANK_FEES"


def test_a_debit_of_a_bank_never_seen_falls_back_to_what_its_code_means_in_the_other_banks():
    assert fallback(txn(-100, bank="NEWB", code="NTRF"), OTHER_BANKS).category == "CUSTOMER_REFUND"
    assert fallback(txn(-100, bank="NEWB", code="UNSEEN"), OTHER_BANKS).category == "BANK_FEES"
