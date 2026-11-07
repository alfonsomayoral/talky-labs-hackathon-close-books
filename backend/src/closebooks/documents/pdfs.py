"""Clauses of the invoice, credit note, proforma and bank-account-notice PDFs as typed facts (POLICIES §5.6-§5.11).
They sit in fixed sentences of the generated documents, in Spanish or English whatever the language of the labels.
Parsers only: nothing here decides a match, and what does not read is recorded and skipped (ARCHITECTURE §7)."""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import re
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta
from importlib.metadata import version
from pathlib import Path

import polars as pl

from .. import paths
from .advices import AdviceError, money, normalize_number, parse_date

FOLDER = "pdfs"
ITEM_TYPE = {"invoice": "ARI", "credit_note": "ARC", "supplier_invoice": "API", "supplier_credit_note": "APC"}
DOC_KIND = {"invoice": "invoicePdf", "supplier_invoice": "invoicePdf", "credit_note": "creditNotePdf",
            "supplier_credit_note": "creditNotePdf", "proforma": "proformaPdf",
            "bank_account_notice": "bankAccountNotice"}
# Only the documents that can carry a clause are read from an earlier phase; the rest is not an item that can be paid.
ALWAYS_READ = {"proforma", "bank_account_notice"}
RETENTION_DAYS = 365
HASH_THREADS = 3  # measured on small PDFs: more threads only fight for the GIL


class PdfError(ValueError):
    """The file is not a PDF this module can read."""


class _Unexpected(str):
    """A failure that says nothing about the file (out of memory, say): reported, but never cached."""


@dataclass(slots=True)
class Clause:
    kind: str
    value: dict


@dataclass(slots=True)
class PdfDoc:
    path: str
    doc_type: str
    number: str
    entity: str
    party_id: str | None
    doc_date: str | None
    clauses: list[Clause] = field(default_factory=list)
    hints: set[str] = field(default_factory=set)  # clause families the text suggests but no regex extracted


# --- scalars -------------------------------------------------------------------------------------------------------

AMOUNT = r"(?:-?\d[\d.,' \u00a0]*\d|\d)"
CUR = r"[A-Z]{3}"
DATE = r"\d{1,2}/\d{1,2}/\d{4}"
IBAN = r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}"
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _near(doc_date: str | None, days: int = 0) -> date | None:
    return date.fromisoformat(doc_date) + timedelta(days=days) if doc_date else None


def _date(raw: str, near: date | None) -> str | None:
    try:
        return parse_date(raw, near=near)
    except AdviceError:
        return None


def _pct(raw: str) -> int | float:
    number = float(raw.replace(",", "."))
    return int(number) if number == int(number) else number


# --- the sentences ---------------------------------------------------------------------------------------------------

INSTALMENTS = re.compile(
    rf"(\d+)\s+(?:instalments|vencimientos)\s+(?:at|a)\s+(\d+(?:/\d+)*)\s+(?:days|d[ií]as)\s*"
    rf"\(\s*({AMOUNT}(?:\s+/\s+(?:{AMOUNT}))*)\s+({CUR})\s*\)")
RETENTION = re.compile(
    rf"(?:Retention|Retención en garantía del)\s+(\d+(?:[.,]\d+)?)\s*%\s*\(\s*({AMOUNT})\s+({CUR})\s*\)"
    rf"[^()]*\(\s*({DATE})\s*\)\.\s*(?:Amount payable at due date|Importe a pagar al vencimiento):\s*({AMOUNT})")
ADVANCE_EN = re.compile(
    rf"Less advance received(?:\s+against proforma\s+([^\s:]+))?\s*:\s*({AMOUNT})\s+({CUR})\.\s*"
    rf"Net amount due\s+({AMOUNT})")
ADVANCE_ES = re.compile(
    rf"A deducir anticipo recibido(?:\s+según proforma\s+(\S+))?\s+de\s+({AMOUNT})\s+({CUR})\.\s*"
    rf"Importe neto a pagar\s+({AMOUNT})")
REPLACES = re.compile(
    rf"(?:cancels and replaces invoice\s+(\S+)\s+dated|anula y sustituye a la factura\s+(\S+)\s+de)\s+({DATE})")
SERVICE_EN = re.compile(r"service fee for the month of\s+([^\W\d_]+)\s+(\d{4})", re.I)
SERVICE_ES = re.compile(r"servicio técnico correspondiente a\s+([^\W\d_]+)\s+(\d{4})", re.I)
RAPPEL = re.compile(
    rf"(?:Volume rebate|Rappel)\s+[QT](\d)\s+(\d{{4}})(?:\s+por volumen)?\s*\(\s*(\d+(?:[.,]\d+)?)\s*%\s*"
    rf"(?:on|s/)\s+({AMOUNT})\s+({CUR})\s*\)\s*:\s*"
    rf"(to be offset against your next payment|will be paid to your bank account|se compensará en la próxima"
    rf" liquidación|se abonará por transferencia a su cuenta)")
CREDIT = (
    ("offset", re.compile(r"to be deducted from your next payment|se compensará en sus próximos pagos")),
    ("refund", re.compile(r"will be refunded by bank transfer|será reembolsado mediante transferencia bancaria")),
)
FACTORED = re.compile(
    r"(?:has been assigned to|ha sido cedido a)\s+(.+?)\.\s+"
    r"(?:Payment is only discharging|El pago solo será liberatorio)")
NOTICE = re.compile(
    rf"(?:from|a partir del)\s+({DATE})\b.*?\b({IBAN})\b(?:.*?\b({IBAN})\b)?")
MANDATE = re.compile(r"Referencia de mandato:\s*(\S+?)\.?(?:\s|$)")
PAYS_FROM = re.compile(r"payments will be made from|pagos a su favor se realizar", re.I)
DEBITS = re.compile(r"recibos domiciliados|direct debits?", re.I)

# What a document that carries a clause family says without the fixed sentence: the residue for a model.
HINTS = {
    "instalments": re.compile(r"vencimientos|instalments?|plazos|Raten", re.I),
    "retention": re.compile(r"retenci[oó]n|retention|garantía|Einbehalt|retenue|ritenuta|retenção", re.I),
    "advance_deduction": re.compile(r"anticipo|advance received|Anzahlung|acompte|acconto|adiantamento", re.I),
    "replaces": re.compile(r"anula y sustituye|cancels and replaces|replaces invoice|ersetzt|remplace|sostituisce",
                           re.I),
    "service_month": re.compile(r"month of|correspondiente a\s+[^\W\d_]+\s+\d{4}", re.I),
    "rappel": re.compile(r"rappel|volume rebate|rebate", re.I),
    "credit_refund": re.compile(r"deducted from your next|próximos pagos|refunded|reembols", re.I),
    "factored": re.compile(r"assigned to|cedido a|cedida|abgetreten|cédé|ceduto", re.I),
    "new_iban": re.compile(r"bank account|cuenta bancaria|Kontowechsel|changement de compte", re.I),
}
FAMILY = {"rappel_offset": "rappel", "rappel_payout": "rappel"}


def _amounts(raw: str) -> list[int]:
    return [money(part) for part in re.split(r"\s+/\s+", raw)]


def _instalments(text: str, near: date | None) -> list[Clause]:
    found = []
    for match in INSTALMENTS.finditer(text):
        amounts = _amounts(match[3])
        days = [int(d) for d in match[2].split("/")]
        if int(match[1]) == len(amounts) == len(days):
            found.append(Clause("instalments", {"n": len(amounts), "days": days, "amounts": amounts,
                                                "currency": match[4]}))
    return found


def _retention(text: str, near: date | None) -> list[Clause]:
    return [Clause("retention", {
        "pct": _pct(m[1]), "amountCents": money(m[2]), "currency": m[3],
        "releaseDate": _date(m[4], near), "payableCents": money(m[5])}) for m in RETENTION.finditer(text)]


def _advance(text: str, near: date | None) -> list[Clause]:
    return [Clause("advance_deduction", {
        "amountCents": money(m[2]), "proforma": m[1], "netDueCents": money(m[4]), "currency": m[3]})
        for rx in (ADVANCE_EN, ADVANCE_ES) for m in rx.finditer(text)]


def _replaces(text: str, near: date | None) -> list[Clause]:
    return [Clause("replaces", {"replaces": m[1] or m[2], "date": _date(m[3], near)}) for m in REPLACES.finditer(text)]


def _service_month(text: str, near: date | None) -> list[Clause]:
    months = {(MONTHS[m[1].lower()], int(m[2])) for rx in (SERVICE_EN, SERVICE_ES) for m in rx.finditer(text)
              if m[1].lower() in MONTHS}
    return [Clause("service_month", {"month": month, "year": year}) for month, year in sorted(months)]


def _rappel(text: str, near: date | None) -> list[Clause]:
    return [Clause("rappel_offset" if m[6].startswith(("to be offset", "se compensará")) else "rappel_payout", {
        "quarter": int(m[1]), "year": int(m[2]), "pct": _pct(m[3]), "baseCents": money(m[4]), "currency": m[5]})
        for m in RAPPEL.finditer(text)]


def _credit(text: str, near: date | None) -> list[Clause]:
    return [Clause("credit_refund", {"mode": mode}) for mode, rx in CREDIT if rx.search(text)]


def _factored(text: str, near: date | None) -> list[Clause]:
    return [Clause("factored", {"factor": m[1].strip()}) for m in FACTORED.finditer(text)]


def _notice(text: str, near: date | None) -> list[Clause]:
    match = NOTICE.search(text)
    if not match:
        return []
    value = {"iban": match[2], "previous": match[3], "from": _date(match[1], near),
             "via": "direct_debit" if DEBITS.search(text) and not PAYS_FROM.search(text) else "payment"}
    if mandate := MANDATE.search(text):
        value["mandate"] = mandate[1]
    return [Clause("new_iban", value)]


EXTRACTORS = (_instalments, _retention, _advance, _replaces, _service_month, _rappel, _credit, _factored, _notice)


def clauses_from_text(text: str, doc_date: str | None = None) -> list[Clause]:
    """Every clause of a document's text, in any wrapping: the sentences are matched over the text with its whitespace
    collapsed. `doc_date` (ISO) resolves day-first or month-first dates by closeness."""
    flat = " ".join(text.split()).split("Documento sint")[0]
    found: list[Clause] = []
    for extract in EXTRACTORS:
        near = _near(doc_date, RETENTION_DAYS if extract is _retention else 0)
        found += extract(flat, near)
    return found


def unextracted_hints(text: str, found: list[Clause]) -> set[str]:
    """Clause families the text insinuates and no clause of `found` covers."""
    flat = " ".join(text.split()).split("Documento sint")[0]
    extracted = {FAMILY.get(c.kind, c.kind) for c in found}
    return {family for family, rx in HINTS.items() if family not in extracted and rx.search(flat)}


# --- pdf -----------------------------------------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    from pypdf import PdfReader

    try:
        text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    except Exception as err:  # corrupt or truncated pdf: whatever the library raises, the file is the problem
        raise PdfError(f"unreadable pdf: {type(err).__name__}: {err}") from err
    if not text.strip():
        raise PdfError("no text")
    return text


def parse_pdf(path: Path, doc_date: str | None = None) -> list[Clause]:
    return clauses_from_text(_read_text(Path(path)), doc_date)


def _parse_one(path: Path, doc_date: str | None) -> tuple[list[Clause], set[str]]:
    text = _read_text(path)
    found = clauses_from_text(text, doc_date)
    return found, unextracted_hints(text, found)


def _parse_chunk(chunk: list[tuple[str, str | None]]) -> list[tuple[list[Clause], set[str]] | str]:
    out = []
    for path, doc_date in chunk:
        try:
            out.append(_parse_one(Path(path), doc_date))
        except PdfError as err:
            out.append(str(err))
        except Exception as err:  # a dirty document must never take the run down
            out.append(_Unexpected(f"{type(err).__name__}: {err}"))
    return out


# --- the phase ---------------------------------------------------------------------------------------------------

class PdfFacts:
    def __init__(self, docs: list[PdfDoc], failures: list[tuple[str, str]], item_ids: dict[int, str],
                 failed_types: dict[str, int]):
        self.docs = docs
        self.failures = failures
        self.failed_types = failed_types
        self._by_number: dict[tuple[str, str], list[PdfDoc]] = {}
        self._by_item: dict[str, PdfDoc] = {}
        for i, doc in enumerate(docs):
            self._by_number.setdefault((doc.entity, normalize_number(doc.number)), []).append(doc)
            if i in item_ids:
                self._by_item[item_ids[i]] = doc

    def doc_for_item(self, item_id: str) -> PdfDoc | None:
        return self._by_item.get(item_id)

    def has_pdf(self, item_id: str) -> bool:
        return item_id in self._by_item

    def for_item(self, item_id: str) -> list[Clause]:
        doc = self._by_item.get(item_id)
        return doc.clauses if doc else []

    def for_number(self, entity: str, number: str, doc_type: str | None = None) -> list[Clause]:
        """Clauses of the documents of `entity` printed with this number (any prefix or zero style)."""
        return [c for d in self._by_number.get((entity, normalize_number(number)), [])
                if doc_type is None or d.doc_type == doc_type for c in d.clauses]

    def notices(self, party_id: str | None = None) -> list[tuple[PdfDoc, Clause]]:
        """The new-account notices, optionally of one customer or supplier."""
        return [(d, c) for d in self.docs if d.doc_type == "bank_account_notice"
                if party_id is None or d.party_id == party_id for c in d.clauses if c.kind == "new_iban"]


def _norm(column: str) -> pl.Expr:
    """normalize_number, as an expression: the printed number without separators or case, digits without zeros."""
    text = pl.col(column).str.replace_all(r"[^0-9A-Za-z]", "").str.to_uppercase()
    return pl.when(text.str.contains(r"^\d+$")).then(text.str.strip_chars_start("0")).otherwise(text)


def _index(folder: Path) -> pl.DataFrame:
    path = folder / FOLDER / "index.csv"
    frame = pl.read_csv(path, infer_schema_length=0) if path.exists() else pl.DataFrame(schema={
        c: pl.String for c in ("file", "document_type", "document_number", "entity", "party_id", "document_date")})
    return frame.with_columns(
        pl.lit(str(folder)).alias("folder"), pl.col("document_type").replace_strict(ITEM_TYPE, default=None).alias(
            "item_type"), _norm("document_number").alias("norm"))


def _wanted(phase) -> pl.DataFrame:
    """Every PDF of the phase, and of the earlier phases the ones an item still open can need: the invoice of a
    carried-over item is in the phase that issued it."""
    own = _index(Path(phase.dir))
    prior = [_index(Path(p)) for p in getattr(phase, "prior", [])]
    if not prior:
        return own
    keys = ["item_type", "entity", "norm"]
    open_items = phase.items.filter(pl.col("open_cents") > 0).select(
        "item_type", "entity", _norm("document_number").alias("norm")).unique()
    older = pl.concat(prior)
    needed = older.filter(pl.col("document_type").is_in(list(ALWAYS_READ))).vstack(
        older.join(open_items, on=keys, how="semi"))
    return pl.concat([own, needed])


def _cache_version() -> str:
    """What the facts of a file depend on besides the file: this parser, the helpers it imports and pypdf."""
    code = b"".join(Path(__file__).with_name(name).read_bytes() for name in ("pdfs.py", "advices.py"))
    return hashlib.sha256(code + version("pypdf").encode()).hexdigest()[:16]


def _cache_file() -> Path:
    return paths.RUNS / "cache" / FOLDER / f"{_cache_version()}.pkl"


def _read_cache() -> dict:
    try:
        return pickle.loads(_cache_file().read_bytes())
    except Exception:  # missing, cut or from another Python: whatever it is, it only means reading the files again
        return {}


def _write_cache(entries: dict) -> None:
    path = _cache_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(f".{os.getpid()}.tmp")
    partial.write_bytes(pickle.dumps(entries, protocol=pickle.HIGHEST_PROTOCOL))
    partial.replace(path)


def _cache_key(job: tuple[str, str | None]) -> tuple[str, str | None] | None:
    """The file's content and its date, which fixes the year of a date printed without one."""
    try:
        return hashlib.sha256(Path(job[0]).read_bytes()).hexdigest(), job[1]
    except OSError:
        return None


def _parse_all(jobs: list[tuple[str, str | None]], workers: int | None = None) -> list:
    """Facts per file in the order given. A file read by an earlier run, here or in another phase, is not read again."""
    known = _read_cache()
    with ThreadPoolExecutor(HASH_THREADS) as threads:
        keys = list(threads.map(_cache_key, jobs))
    fresh = iter(_parse_missing([job for job, key in zip(jobs, keys, strict=True) if key not in known], workers))
    results, new = [], {}
    for key in keys:
        if key in known:
            results.append(known[key])
            continue
        results.append(next(fresh))
        if key is not None and not isinstance(results[-1], _Unexpected):
            new[key] = results[-1]
    if new:
        _write_cache({**known, **new})
    return results


def _parse_missing(jobs: list[tuple[str, str | None]], workers: int | None = None) -> list:
    workers = workers or min(6, os.cpu_count() or 1)
    if workers == 1 or len(jobs) < 2 * workers:
        return _parse_chunk(jobs)
    size = max(1, len(jobs) // (workers * 8))
    chunks = [jobs[i:i + size] for i in range(0, len(jobs), size)]
    with ProcessPoolExecutor(workers) as pool:
        return [x for chunk in pool.map(_parse_chunk, chunks) for x in chunk]


_CACHE: dict[tuple, PdfFacts] = {}


def _build(phase) -> PdfFacts:
    wanted = _wanted(phase).with_row_index("i")
    rows = list(wanted.iter_rows(named=True))
    results = _parse_all([(str(Path(r["folder"]) / FOLDER / r["file"]), r["document_date"]) for r in rows])
    docs: list[PdfDoc] = []
    failures: list[tuple[str, str]] = []
    failed_types: dict[str, int] = {}
    kept: list[int] = []
    for row, result in zip(rows, results, strict=True):
        path = f"{FOLDER}/{row['file']}"
        if isinstance(result, str):
            failures.append((path, result))
            failed_types[row["document_type"]] = failed_types.get(row["document_type"], 0) + 1
            continue
        found, hints = result
        kept.append(row["i"])
        docs.append(PdfDoc(path, row["document_type"], row["document_number"], row["entity"], row["party_id"],
                           row["document_date"], found, hints))
    items = phase.items.select("item_id", "item_type", "entity", _norm("document_number").alias("norm")).unique(
        ["item_type", "entity", "norm"])
    matched = wanted.filter(pl.col("i").is_in(kept)).join(items, on=["item_type", "entity", "norm"])
    position = {i: n for n, i in enumerate(kept)}
    item_ids = {position[i]: item_id for i, item_id in matched.select("i", "item_id").iter_rows()}
    return PdfFacts(docs, failures, item_ids, failed_types)


def phase_clauses(phase) -> PdfFacts:
    """The clauses of the phase's PDFs (and the earlier phases' that an open item needs), read once per process:
    the rules and the facts share them."""
    key = (str(phase.dir), tuple(str(p) for p in getattr(phase, "prior", [])))
    if key not in _CACHE:
        _CACHE[key] = _build(phase)
    return _CACHE[key]


def clauses_frame(facts: PdfFacts) -> pl.DataFrame:
    """The rows of facts/documents.parquet (CONTRACT §2.3) for the PDFs: one per clause, method `parser`."""
    from ..output import DOCUMENT_SCHEMA

    rows = []
    for doc in facts.docs:
        for n, clause in enumerate(doc.clauses, 1):
            value = dict(clause.value, partyId=doc.party_id) if clause.kind == "new_iban" else clause.value
            rows.append((doc, n, clause, json.dumps(value, ensure_ascii=False, separators=(",", ":"))))
    empty = [None] * len(rows)
    return pl.DataFrame({
        "docPath": [d.path for d, *_ in rows], "docKind": [DOC_KIND[d.doc_type] for d, *_ in rows],
        "entity": [d.entity for d, *_ in rows], "payerName": empty, "receivedDate": empty, "paymentRef": empty,
        "paymentDate": empty, "paymentTotalCents": empty, "currency": [c.value.get("currency") for _, _, c, _ in rows],
        "lineNo": [n for _, n, _, _ in rows], "documentNumber": [d.number for d, *_ in rows],
        "documentNumberNorm": [normalize_number(d.number) for d, *_ in rows], "grossCents": empty,
        "deductionCents": empty, "reason": empty, "paidCents": empty, "customerPo": empty, "voucher": empty,
        "clause": [c.kind for _, _, c, _ in rows], "clauseValue": [v for *_, v in rows],
        "method": ["parser"] * len(rows), "model": empty, "cacheKey": empty,
    }, schema=DOCUMENT_SCHEMA)


def residue(facts: PdfFacts) -> dict[str, dict[str, int]]:
    """Per document type: PDFs read, with a clause, whose text hints at a clause that was not extracted, and files that
    did not read. What is hinted and not extracted is for the model."""
    out: dict[str, dict[str, int]] = {}
    for doc in facts.docs:
        counts = out.setdefault(doc.doc_type, {"read": 0, "with_clause": 0, "hinted_unextracted": 0, "failed": 0})
        counts["read"] += 1
        counts["with_clause"] += bool(doc.clauses)
        counts["hinted_unextracted"] += bool(doc.hints)
    for kind, failed in facts.failed_types.items():
        out.setdefault(kind, {"read": 0, "with_clause": 0, "hinted_unextracted": 0, "failed": 0})["failed"] = failed
    return out
