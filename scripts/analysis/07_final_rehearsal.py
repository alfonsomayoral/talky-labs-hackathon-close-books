"""A rehearsal of FINAL: a copy of a phase where one entity has a code, a bank, a format and a currency never seen.

Nothing changes in value: amounts stay, the new currency has the old one's rates. So any drop against the source phase
is a rule that depended on a name, not on the data. db/holdout-drift mutates the data as well; this isolates the names.

    cd backend
    uv run python ../scripts/analysis/07_final_rehearsal.py build
    uv run closebooks run --phase holdout-final --out ../runs/final-rehearsal
    uv run closebooks validate ../runs/final-rehearsal/submission.csv.gz --phase holdout-final
    uv run python ../scripts/analysis/07_final_rehearsal.py report ../runs/<holdout run> ../runs/final-rehearsal

Differences with a real FINAL, on purpose or not: the entity keeps its customers and history, while ZA01 arrives with
none; its numbering is the old one; invoice PDFs keep the old currency in their text (only advices are rewritten);
closed items of earlier phases keep the old code, so a new line that cites one finds nothing (the report counts them).
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
from collections import Counter
from pathlib import Path

import polars as pl
from openpyxl import load_workbook
from pypdf import PdfReader, PdfWriter

from closebooks.holdout import DETAIL_FOLDERS, _fresh, _link, _write_gz
from closebooks.load import load_table
from closebooks.paths import DB, masters_dir, phase_dir

ID_COLUMNS = ("entity", "account_id", "debtor_account_id", "customer_id", "supplier_id", "party_id", "group_id",
              "parent_customer_id", "statement_file")
ITEM_TABLES = ("ar_invoices", "ap_invoices", "credit_notes", "open_items_at_start")
MASTER_TABLES = ("categories", "payment_terms")


class Rename:
    def __init__(self, entity: str, bank: str, currency: str, new_entity: str, new_bank: str, new_currency: str,
                 new_format: str):
        self.entity, self.bank, self.currency = entity, bank, currency
        self.new_entity, self.new_bank, self.new_currency, self.new_format = (new_entity, new_bank, new_currency,
                                                                              new_format)
        self.word = re.compile(rf"\b{currency}\b")

    def ids(self, table: pl.DataFrame) -> list[pl.Expr]:
        """Ids carry the code of their entity; accounts also its bank and currency."""
        exprs = []
        for column in table.columns:
            if column not in ID_COLUMNS:
                continue
            expr = pl.col(column).str.replace_all(self.entity, self.new_entity, literal=True)
            if column in ("account_id", "debtor_account_id", "statement_file"):
                prefix = f"{self.new_entity}-{self.bank}"
                expr = expr.str.replace_all(prefix, f"{self.new_entity}-{self.new_bank}", literal=True).str.replace_all(
                    f"{self.new_entity}-{self.new_bank}-{self.currency}",
                    f"{self.new_entity}-{self.new_bank}-{self.new_currency}", literal=True)
            exprs.append(expr.alias(column))
        return exprs

    def money(self, column: str, mine: pl.Expr) -> pl.Expr:
        return pl.when(mine & (pl.col(column) == self.currency)).then(pl.lit(self.new_currency)).otherwise(
            pl.col(column)).alias(column)

    def items(self, table: pl.DataFrame) -> pl.DataFrame:
        return table.with_columns(self.money("currency", pl.col("entity") == self.entity), *self.ids(table))

    def txns(self, table: pl.DataFrame) -> pl.DataFrame:
        mine = pl.col("entity") == self.entity
        words = [pl.when(mine).then(pl.col(c).str.replace_all(rf"\b{self.currency}\b", self.new_currency))
                 .otherwise(pl.col(c)).alias(c) for c in ("text", "remittance_info")]
        return table.with_columns(
            self.money("currency", mine), self.money("orig_currency", mine), *words,
            pl.when(mine).then(pl.lit(self.new_bank)).otherwise(pl.col("bank")).alias("bank"),
            pl.when(mine).then(pl.lit(self.new_format)).otherwise(pl.col("statement_format")).alias("statement_format"),
        ).with_columns(self.ids(table))

    def detail(self, source: Path, target: Path) -> None:
        """Only the files that name the entity are rewritten; the factory of another entity can pay for it."""
        if self.entity.encode() not in source.read_bytes():
            _link(source, target)
            return
        table = load_table(source)
        exprs = self.ids(table)
        if "currency" in table.columns:
            exprs.append(self.money("currency", pl.lit(True)))
        target.parent.mkdir(parents=True, exist_ok=True)
        table.with_columns(exprs).write_csv(target)

    def masters(self, source: Path, target: Path, with_rate: bool = True) -> None:
        target.mkdir()
        for name in MASTER_TABLES:
            shutil.copy(source / f"{name}.csv", target / f"{name}.csv")
        mine = pl.col("entity") == self.entity
        table = load_table(source / "entities.csv")
        table.with_columns(self.money("functional_currency", mine), *self.ids(table)).write_csv(target / "entities.csv")
        table = load_table(source / "bank_accounts.csv")
        table.with_columns(
            self.money("currency", mine),
            pl.when(mine).then(pl.lit(self.new_bank)).otherwise(pl.col("bank")).alias("bank"),
            pl.when(mine).then(pl.lit(self.new_format)).otherwise(pl.col("statement_format")).alias("statement_format"),
        ).with_columns(self.ids(table)).write_csv(target / "bank_accounts.csv")
        for name in ("customers", "suppliers"):
            table = load_table(source / f"{name}.csv")
            table.with_columns(self.money("invoice_currency", mine), *self.ids(table)).write_csv(target / f"{name}.csv")
        rates = load_table(source / "fx_rates.csv")
        if self.new_currency in rates["currency"].to_list():
            raise SystemExit(f"{self.new_currency} is already in the FX file: it would not be a new currency")
        same = rates.filter(pl.col("currency") == self.currency).with_columns(
            pl.lit(self.new_currency).alias("currency"))
        if same.is_empty():  # the euro has no rates: the new currency stands at one everywhere
            same = rates.select("date").unique().sort("date").with_columns(
                pl.lit(self.new_currency).alias("currency"), pl.lit("1.0").alias("units_per_eur"),
                pl.lit("rehearsal").alias("source"))
        kept = [rates, same.select(rates.columns)] if with_rate else [rates]
        pl.concat(kept).write_csv(target / "fx_rates.csv")

    def advice(self, source: Path, target: Path) -> None:
        """The currency a customer prints, in each format; amounts and references stay."""
        target.parent.mkdir(parents=True, exist_ok=True)
        old, new = self.currency, self.new_currency
        if source.suffix.lower() == ".xlsx":
            book = load_workbook(source)
            for sheet in book:
                for row in sheet.iter_rows():
                    for cell in row:
                        if isinstance(cell.value, str):
                            cell.value = self.word.sub(new, cell.value)
            book.save(target)
        elif source.suffix.lower() == ".pdf":
            writer = PdfWriter(clone_from=PdfReader(source))
            for page in writer.pages:
                contents = page.get_contents()
                contents.set_data(contents.get_data().replace(old.encode(), new.encode()))
                page.replace_contents(contents)
            writer.write(target)
        else:
            target.write_bytes(re.sub(rf"\b{old}\b".encode(), new.encode(), source.read_bytes()))

    def documents(self, source: Path, out: Path, prior: list[Path], opening: pl.DataFrame | None) -> None:
        folder = "remittance_advices"
        index = load_table(source / folder / "index.csv")
        (out / folder).mkdir(parents=True)
        for name in index["file"].to_list():
            new = self._moved(name)
            if name.startswith(f"{self.entity}/"):
                self.advice(source / folder / name, out / folder / new)
            else:
                _link(source / folder / name, out / folder / new)
        moved = pl.col("file").map_elements(self._moved, return_dtype=pl.String)
        index.with_columns(moved, *self.ids(index)).write_csv(out / folder / "index.csv")

        folder = "pdfs"
        index = load_table(source / folder / "index.csv")
        origin = {name: source / folder / name for name in index["file"].to_list()}
        # Carried items find their PDF in an earlier phase by entity, and that one still has the old code.
        if opening is not None:
            numbers = opening.filter(pl.col("entity") == self.new_entity).select("document_number").unique()
            for phase in prior:
                older = load_table(phase / folder / "index.csv").filter(pl.col("entity") == self.entity).join(
                    numbers, on="document_number", how="semi").select(index.columns)
                older = older.filter(~pl.col("file").is_in(list(origin)))
                origin |= {name: phase / folder / name for name in older["file"].to_list()}
                index = pl.concat([index, older])
        (out / folder).mkdir(parents=True)
        for name, path in origin.items():
            _link(path, out / folder / self._moved(name))
        moved = pl.col("file").map_elements(self._moved, return_dtype=pl.String)
        index.with_columns(moved, *self.ids(index)).write_csv(out / folder / "index.csv")

    def _moved(self, name: str) -> str:
        return name.replace(f"{self.entity}/", f"{self.new_entity}/", 1) if name.startswith(self.entity) else name


def main_bank_and_currency(masters: Path, entity: str) -> tuple[str, str]:
    """The entity's functional currency and the bank of its account in it."""
    currency = load_table(masters / "entities.csv").filter(pl.col("entity") == entity)["functional_currency"][0]
    accounts = load_table(masters / "bank_accounts.csv").filter(pl.col("entity") == entity)
    banks = accounts["bank"].unique().to_list()
    if len(banks) != 1:
        raise SystemExit(f"{entity} has the banks {banks}: choose an entity with one")
    return banks[0], currency


def build(source_name: str, dest_name: str, entity: str, new_entity: str, new_bank: str, new_currency: str,
          new_format: str, with_rate: bool = True, with_history: bool = True) -> Path:
    source = phase_dir(source_name)
    out = _fresh(DB / dest_name)
    masters = masters_dir(source)
    bank, currency = main_bank_and_currency(masters, entity)
    rename = Rename(entity, bank, currency, new_entity, new_bank, new_currency, new_format)

    txns = load_table(source / "bank_transactions.csv.gz")
    _write_gz(rename.txns(txns), out / "bank_transactions.csv.gz")
    opening = None
    for name in ITEM_TABLES:
        path = source / f"{name}.csv.gz"
        if path.exists():
            table = rename.items(load_table(path))
            if name == "open_items_at_start" and not with_history:  # as ZA01 arrives: nothing carried over
                table = table.filter(pl.col("entity") != new_entity)
            _write_gz(table, out / f"{name}.csv.gz")
            if name == "open_items_at_start":
                opening = table
    if (source / "golden_allocations.csv.gz").exists():
        shutil.copy(source / "golden_allocations.csv.gz", out / "golden_allocations.csv.gz")
    for folder in DETAIL_FOLDERS:
        for file in sorted((source / folder).glob("*.csv")):
            rename.detail(file, out / folder / file.name.replace(entity, new_entity, 1))
    _link(source / "bank_statements", out / "bank_statements")
    rename.masters(masters, out / "masters_final", with_rate)
    prior = []
    if (source / "prior_phases").exists():
        shutil.copy(source / "prior_phases", out / "prior_phases")
        prior = [phase_dir(p) for p in (source / "prior_phases").read_text().split()]
    rename.documents(source, out, prior, opening)
    return out


def _rows(run: Path) -> dict[str, list[tuple]]:
    table = pl.read_csv(run / "submission.csv.gz", infer_schema_length=0)
    rows: dict[str, list[tuple]] = {}
    for row in table.iter_rows():
        rows.setdefault(row[0], []).append(row[1:])
    return rows


def _rules(run: Path) -> dict[str, str]:
    with gzip.open(run / "explanations.jsonl.gz", "rt") as lines:
        return {e["bankTxnId"]: e["rule"] for e in map(json.loads, lines)}


def report(base: Path, final: Path, phase_name: str, new_entity: str) -> None:
    """Which bank lines changed, where and to what rule; and the score by segment, the ones that drop first."""
    before, after = _rows(base), _rows(final)
    changed = [t for t in before if before[t] != after.get(t)]
    entity = dict(load_table(phase_dir(phase_name) / "bank_transactions.csv.gz").select(
        "bank_txn_id", "entity").iter_rows())
    rule_before, rule_after = _rules(base), _rules(final)
    print(f"bank lines {len(before)}, changed {len(changed)}")
    print("changed by entity:", Counter(entity[t] for t in changed).most_common())
    print("rule before -> after:")
    for (a, b), n in Counter((rule_before[t], rule_after[t]) for t in changed).most_common(30):
        print(f"  {n:6d}  {a} -> {b}")
    meta_before, meta_after = (json.loads((r / "run.json").read_text()) for r in (base, final))
    if meta_before.get("score") and meta_after.get("score"):
        print("score", meta_before["score"]["score"], "->", meta_after["score"]["score"])
        segments = meta_before["score"]["segments"]
        drops = sorted(((meta_after["score"]["segments"][s]["accuracy"] - v["accuracy"], s, v["n"])
                        for s, v in segments.items() if v != meta_after["score"]["segments"].get(s)))
        for delta, segment, n in drops:
            print(f"  {delta:+.4f}  {segment}  n={n}")
    print("sample of changed lines:", [t for t in changed if entity[t] == new_entity][:10])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    made = sub.add_parser("build")
    made.add_argument("--source", default="holdout")
    made.add_argument("--dest", default="holdout-final")
    made.add_argument("--entity", default="MA01")
    made.add_argument("--new-entity", default="XX01")
    made.add_argument("--new-bank", default="QNTM")
    made.add_argument("--new-currency", default="HUF")
    made.add_argument("--new-format", default="mt940x")
    made.add_argument("--no-rate", action="store_true", help="the new currency has no line in the FX file")
    made.add_argument("--no-history", action="store_true", help="the new entity carries nothing from earlier phases")
    told = sub.add_parser("report")
    told.add_argument("base", type=Path)
    told.add_argument("final", type=Path)
    told.add_argument("--phase", default="holdout-final")
    told.add_argument("--new-entity", default="XX01")
    args = parser.parse_args()
    if args.command == "build":
        print(build(args.source, args.dest, args.entity, args.new_entity, args.new_bank, args.new_currency,
                    args.new_format, not args.no_rate, not args.no_history))
    else:
        report(args.base, args.final, args.phase, args.new_entity)


if __name__ == "__main__":
    main()
