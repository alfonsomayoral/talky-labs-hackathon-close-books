"""Small DuckDB helpers shared by the run and the phase tables."""
from __future__ import annotations

from pathlib import Path

from ..paths import master_path


def lit(path: Path | str) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def read_csv(path: Path) -> str:
    """Everything as text, with the dialect fixed: sniffing a file full of quoted commas gets it wrong."""
    return f"read_csv({lit(path)}, all_varchar=true, header=true, delim=',', quote='\"', escape='\"')"


def create_party(con, phase: Path) -> None:
    """Customers and suppliers of the phase's masters, as the `Party` of the API."""
    con.execute(f"""CREATE TABLE party AS
        SELECT customer_id AS "partyId", 'customer' AS kind, entity, name, trade_name AS "tradeName",
               customer_type AS type, country, tax_id AS "taxId", iban, payment_terms AS "paymentTerms",
               invoice_currency AS currency, group_id AS "groupId", parent_customer_id AS "parentId",
               blocked_since AS "blockedSince" FROM {read_csv(master_path(phase, "customers.csv"))}
        UNION ALL
        SELECT supplier_id, 'supplier', entity, name, NULL, supplier_type, country, tax_id, iban,
               payment_terms, invoice_currency, NULL, NULL, blocked_since
        FROM {read_csv(master_path(phase, "suppliers.csv"))}""")
