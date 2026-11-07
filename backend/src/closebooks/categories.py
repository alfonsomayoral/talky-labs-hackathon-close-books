"""Lines that settle no item (POLICIES §4): what the bank code and the text say, and the fallback."""
from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import polars as pl

from .paths import category_codes_path

ITEM = "ITEM"  # label in the table for a line that settles items
MIN_SUPPORT = 10  # lines a combination needs in the history before its code decides alone

Codes = dict[tuple[str, str, str, str], Counter]  # (bank, code, subcode, direction) -> label -> lines

# (direction or None for both, pattern on the bank text, category). Keywords that only these lines carry in TRAIN.
TEXT_RULES = (
    (None, r"ANULACION OPERACION INDEBIDA|^(?:RECIBO|COMISION|ABONO|TRANSFERENCIA RECIBIDA|SEG\. SOCIAL COTIZ\.)$",
     "BANK_REVERSAL"),  # the wrong booking carries only a generic word; its cancellation says "indebida"
    (None, r"CASH CONCENTRATION|ZBA SWEEP|CASH POOL|TRASPASO PROPIO|TRASPASO ENTRE CUENTAS", "CASH_POOL"),
    (None, r"\bTRASPASO (?:A|DE) CTA\b", "INTERNAL_TRANSFER"),
    (None, r"\b(?:TRANSF\.|FINANCIACION|FINANCING|PRESTAMO) IC\b|\bINTERCOMPANY\b|\bINTRAGRUP", "INTERCOMPANY"),
    (None, r"\bFX DEAL\b|\b(?:COMPRA|VENTA) DIVISA\b", "FX_DEAL"),
    ("debit", r"\bNOMINAS?\b|\bPAYROLL\b", "PAYROLL"),
    ("debit", r"SOCIAL CHARGES|\bTGSS\b|SEGURIDAD SOCIAL", "SOCIAL_SECURITY"),
    ("debit", r"IMPUESTOS MOD|TAX PAYMENT|TAX AUTHORITY|VAT RETURN|\bDGFIP\b", "TAX_PAYMENT"),
    ("credit", r"DEVOLUCION AEAT", "TAX_REFUND"),
    ("debit", r"ADEUDO MENSUAL DE TARJETA", "CARD_EXPENSES"),
    ("debit", r"\bCUOTA (?:LEASING|ARRENDAMIENTO|LSG|RENTING)\b", "LEASING"),
    ("debit", r"INSURANCE PREMIUM|PRIMA SEGURO|SEGUROS MULTIRRIESGO", "INSURANCE"),
    ("debit", r"AMORTIZACION|\bPRES\.[A-Z]{2}\d", "LOAN_REPAYMENT"),
    ("credit", r"DISPOSICION POLIZA", "LOAN_DRAWDOWN"),
    ("credit", r"LIQUIDACION INTERESES", "INTEREST_INCOME"),
    ("debit", r"LIQUIDACION INTERESES", "INTEREST_EXPENSE"),
    ("credit", r"PROFORMA|\bPF\d{2,}-\d", "CUSTOMER_ADVANCE"),
    # Our refund of a duplicate. The supplier's refund of a credit note cites "REEMBOLSO FRA <invoice>": an item.
    ("debit", r"REFUND|DUPLICAD", "CUSTOMER_REFUND"),
    ("credit", r"PAGO DOBLE|DUPLICAD|REEMBOLSO(?! FRA\b)", "SUPPLIER_REFUND"),
)
_TEXT_RULES = tuple((d, re.compile(p), c) for d, p, c in TEXT_RULES)


class NoItem(NamedTuple):
    category: str
    exception: str
    rule: str
    confidence: float


def direction(amount_cents: int) -> str:
    return "credit" if amount_cents > 0 else "debit"


@lru_cache(maxsize=4)
def _read(path: Path) -> Codes:
    codes: Codes = {}
    for row in pl.read_csv(path, schema_overrides={"bank_subcode": pl.String, "bank_code": pl.String}).fill_null(
            "").iter_rows(named=True):
        codes.setdefault((row["bank"], row["bank_code"], row["bank_subcode"], row["direction"]), Counter())[
            row["label"]] = row["count"]
    return codes


def load_codes(path: Path | None = None) -> Codes:
    return _read(path or category_codes_path())


def combination(txn: dict) -> tuple[str, str, str, str]:
    return txn["bank"], txn["bank_code"] or "", txn["bank_subcode"] or "", direction(txn["amount_cents"])


def _history(codes: Codes, txn: dict) -> Counter | None:
    """The lines of this combination. A bank never seen has none of its own: what its code did in all the others."""
    key = combination(txn)
    if key in codes or any(known[0] == key[0] for known in codes):
        return codes.get(key)
    together: Counter = Counter()
    for (_, *rest), counts in codes.items():
        if tuple(rest) == key[1:]:
            together.update(counts)
    return together or None


def pure_category(codes: Codes, txn: dict) -> str | None:
    """The category when every line of this code in the history has it, none settled items and there are enough."""
    counts = _history(codes, txn)
    if not counts or len(counts) != 1:
        return None
    (label, lines), = counts.items()
    return label if label != ITEM and lines >= MIN_SUPPORT else None


def text_category(txn: dict) -> str | None:
    text = (txn["text"] or "").upper()
    side = direction(txn["amount_cents"])
    for wanted, pattern, category in _TEXT_RULES:
        if wanted in (None, side) and pattern.search(text):
            return category
    return None


def likely_category(codes: Codes, txn: dict) -> str | None:
    """The most frequent category of the code among the lines that settle no item."""
    counts = {k: n for k, n in (_history(codes, txn) or {}).items() if k != ITEM}
    return min(counts, key=lambda k: (-counts[k], k)) if counts else None


def fallback(txn: dict, codes: Codes | None = None) -> NoItem:
    """No evidence: a receipt is UNIDENTIFIED (never forced); a debit gets the category its code points to."""
    if txn["amount_cents"] > 0:
        return NoItem("UNIDENTIFIED", "UNIDENTIFIED", "FALLBACK-UNIDENTIFIED", 0.0)
    category = likely_category(load_codes() if codes is None else codes, txn)
    return NoItem(category or "BANK_FEES", "", "FALLBACK-CATEGORY", 0.0)
