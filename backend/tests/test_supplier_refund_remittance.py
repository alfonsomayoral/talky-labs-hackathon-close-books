from closebooks.rules.categories import claim


def test_supplier_refund_read_from_remittance_field():
    # BT-2025-0013372 (holdout): the bank text is a generic ACH line; "ABONO PAGO DOBLE" is in the remittance field.
    txn = {"bank_txn_id": "BT-2025-0013372", "bank": "HPNB", "bank_code": "PMNT/RCDT/ESCT", "bank_subcode": "",
           "amount_cents": 686735, "text": "ACH CREDIT CHEMICALS EXPRES CCD PAYMENT ID:9150765539",
           "remittance_info": "ABONO PAGO DOBLE"}
    proposal = claim(txn, {})
    assert proposal is not None and proposal.category == "SUPPLIER_REFUND"
