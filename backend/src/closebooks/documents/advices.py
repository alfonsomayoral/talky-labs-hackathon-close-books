"""Remittance advices (csv, txt, xlsx, pdf) as typed facts. They are dirty, untrusted documents: what does not parse
is recorded and skipped, what does not add up is kept but flagged. Parsers only: no model (ARCHITECTURE §7)."""
from __future__ import annotations

import csv
import email.utils
import io
import os
import re
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

import polars as pl

FOLDER = "remittance_advices"
KINDS = {".csv": "csv", ".txt": "txt", ".xlsx": "xlsx", ".pdf": "pdf"}

MAX_WORKERS = 6  # a bound on memory: FINAL runs with the platform up; two kernel panics came from exhausting it


class AdviceError(ValueError):
    """The file is not an advice this module knows how to read."""


@dataclass(slots=True)
class AdviceLine:
    line_no: int
    document: str
    doc_date: str | None
    gross_cents: int | None
    deduction_cents: int
    reason: str | None
    paid_cents: int
    po: str | None = None
    voucher: str | None = None

    @property
    def shortfall_cents(self) -> int:
        """Paid minus gross, whether or not the advice states a deduction and a reason for it (<= 0 for a short pay)."""
        return self.paid_cents - (self.gross_cents if self.gross_cents is not None else self.paid_cents)


@dataclass(slots=True)
class Advice:
    path: str
    fmt: str
    payment_ref: str | None
    payment_date: str | None
    currency: str | None
    total_cents: int | None
    lines: list[AdviceLine]
    payer: str | None = None
    entity: str | None = None
    received_date: str | None = None

    @property
    def closes(self) -> bool:
        """The paid amounts of the lines add up to the declared total. A line may be paid below its gross without a
        printed deduction (a discount taken silently): that gap is `shortfall_cents`, not a failure to close."""
        return (self.total_cents is not None and bool(self.lines)
                and sum(x.paid_cents for x in self.lines) == self.total_cents)


@dataclass(slots=True)
class AdviceBatch:
    advices: list[Advice] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)  # (relative path, why)


# --- scalars -------------------------------------------------------------------------------------------------------

_NUMBER = re.compile(r"^-?\d[\d.,]*$")


def money(value) -> int | None:
    """Cents from a number as printed: 1,234.56 or 1.234,56 or 1234.56; a cell that is already a number."""
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return int((Decimal(repr(value)) * 100).to_integral_value())
    text = str(value).strip().replace(" ", "").replace("'", "").replace(" ", "")
    if not text:
        return None
    negative = text.startswith("-") or (text.startswith("(") and text.endswith(")"))
    text = text.strip("()-+")
    if not _NUMBER.match(text):
        raise AdviceError(f"not an amount: {value!r}")
    last = max(text.rfind("."), text.rfind(","))
    if last >= 0 and len(text) - last - 1 <= 2:
        whole, fraction = text[:last], text[last + 1:]
    else:
        whole, fraction = text, ""
    digits = re.sub(r"[.,]", "", whole) + "." + (fraction or "0")
    try:
        cents = int((Decimal(digits) * 100).to_integral_value())
    except InvalidOperation as err:
        raise AdviceError(f"not an amount: {value!r}") from err
    return -cents if negative else cents


def parse_date(value, near: date | None = None) -> str | None:
    """ISO date from 2024-10-02, 27/08/2024, 12/04/24 or a date cell. Day first unless `near` says month first is
    closer: advices in English write the payment date month first (12/26/2022)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", text)
    if not match:
        raise AdviceError(f"not a date: {value!r}")
    first, second, year = int(match[1]), int(match[2]), int(match[3])
    year += 2000 if year < 100 else 0
    candidates = []
    for day, month in ((first, second), (second, first)):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            continue
    if not candidates:
        raise AdviceError(f"not a date: {value!r}")
    if near is not None:
        candidates.sort(key=lambda d: abs((d - near).days))
    return candidates[0].isoformat()


def normalize_number(text: str) -> str:
    """The printed number without separators or case; a purely numeric one also without leading zeros."""
    norm = re.sub(r"[^0-9A-Za-z]", "", text or "").upper()
    return norm.lstrip("0") if norm.isdigit() else norm


def _clean(value) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None


# --- tabular formats (csv, xlsx) -----------------------------------------------------------------------------------

COLUMNS = {
    "document": ("document", "invoice"), "voucher": ("voucher",), "po": ("your_order", "po"),
    "doc_date": ("doc_date", "date", "inv. date"), "gross": ("gross", "amount"),
    "deduction": ("discount_or_deduction", "deduction"), "reason": ("reason",), "paid": ("paid", "net paid"),
}


def _columns(header: list, rows: list[list]) -> dict[str, int]:
    names = [str(h or "").strip().lower() for h in header]
    found = {key: names.index(alias) for key, aliases in COLUMNS.items() for alias in aliases if alias in names}
    if "document" not in found or "paid" not in found:
        return _columns_by_content(header, rows)
    return found


_DECIMALS = re.compile(r"[.,]\d{1,2}$")


def _amount_of(cell) -> int | None:
    """Cents of a cell that can only be an amount: a number, or text with decimals. A bare 1102416261 is a document."""
    if isinstance(cell, (int, float, Decimal)):
        return money(cell)
    text = _clean(cell)
    return money(text) if text and _DECIMALS.search(text) and _NUMBER.match(text.lstrip("(-+").rstrip(")")) else None


def _date_of(cell) -> str | None:
    try:
        return parse_date(cell)
    except AdviceError:
        return None


def _columns_by_content(header: list, rows: list[list]) -> dict[str, int]:
    """Headers nobody has seen: the columns by what they hold, only when it can be one column each.

    Paid is where the TOTAL row prints the total, if its lines add up to it. The document number fills every line and
    is neither date nor amount; if another column does too (the customer's order), the number is the one that carries
    the year of the line's date. Whatever is not unequivocal is left out, or the file is rejected as unknown."""
    unknown = AdviceError(f"unknown layout: {header!r}")
    width = len(header)
    grid = [[*r, *[None] * (width - len(r))][:width] for r in rows]
    is_total = [(_clean(r[0]) or "").upper() == "TOTAL" for r in grid]
    lines = [r for r, total in zip(grid, is_total, strict=True) if not total]
    totals = [r for r, total in zip(grid, is_total, strict=True) if total]
    if len(totals) != 1 or not lines:
        raise unknown
    printed = [c for c in range(1, width) if _clean(totals[0][c]) is not None]
    if len(printed) != 1 or _amount_of(totals[0][printed[0]]) is None:
        raise unknown
    paid = printed[0]
    amounts = {c: [_amount_of(r[c]) for r in lines] for c in range(width)}
    if None in amounts[paid] or sum(amounts[paid]) != _amount_of(totals[0][paid]):
        raise unknown
    found = {"paid": paid}
    dates = [c for c in range(width) if all(_date_of(r[c]) for r in lines)]
    if len(dates) == 1:
        found["doc_date"] = dates[0]
    texts = {c: [_clean(r[c]) for r in lines] for c in range(width)}
    numbers = [c for c in range(width) if c not in dates and all(v and any(x.isdigit() for x in v) for v in texts[c])
               and not any(amounts[c])]
    if len(numbers) > 1 and len(dates) == 1:
        numbers = [c for c in numbers if all(
            _date_of(r[dates[0]])[2:4] in str(r[c]) for r in lines)]
    if len(numbers) != 1:
        raise unknown
    found["document"] = numbers[0]
    orders = [c for c in range(width) if c not in (*dates, numbers[0]) and not any(amounts[c]) and any(texts[c])
              and all(not v or any(x.isdigit() for x in v) for v in texts[c])]
    if len(orders) == 1:
        found["po"] = orders[0]
    gross = [c for c in range(width) if c != paid and None not in amounts[c]
             and all(abs(g) >= abs(p) for g, p in zip(amounts[c], amounts[paid], strict=True))]
    if len(gross) == 1:
        found["gross"] = gross[0]
    base = amounts[gross[0]] if len(gross) == 1 else amounts[paid]
    deductions = [c for c in range(width) if c not in (paid, *gross) and any(a is not None for a in amounts[c])
                  and all(a is None or abs(a) == abs(g - p) for a, g, p in zip(amounts[c], base, amounts[paid],
                                                                                strict=True))]
    if len(deductions) == 1:
        found["deduction"] = deductions[0]
    used = set(found.values())
    reasons = [c for c in range(width) if c not in used and any(texts[c])
               and not any(any(x.isdigit() for x in v) for v in texts[c] if v)
               and all(g != p for v, g, p in zip(texts[c], base, amounts[paid], strict=True) if v)]
    if len(reasons) == 1:
        found["reason"] = reasons[0]
    return found


def _table_lines(rows: list[list]) -> tuple[list[AdviceLine], int | None]:
    cols = _columns(rows[0], rows[1:])
    lines: list[AdviceLine] = []
    total = None
    for row in rows[1:]:
        cells = list(row) + [None] * (max(cols.values()) + 1 - len(row))
        number = _clean(cells[cols["document"]])
        if (_clean(cells[0]) or "").upper() == "TOTAL":
            numbers = [money(c) for c in cells[1:] if c is not None and _clean(c) is not None]
            total = numbers[-1] if numbers else None
            continue
        paid = money(cells[cols["paid"]])
        if number is None and paid is None:
            continue
        if number is None or paid is None:
            raise AdviceError(f"incomplete line: {row!r}")
        cell = {key: cells[at] for key, at in cols.items()}
        gross, deduction = money(cell.get("gross")), money(cell.get("deduction")) or 0
        lines.append(AdviceLine(
            len(lines) + 1, number, parse_date(cell.get("doc_date")), gross if gross is not None else paid, deduction,
            _clean(cell.get("reason")), paid, _clean(cell.get("po")), _clean(cell.get("voucher"))))
    return lines, total


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _parse_csv(path: Path, rel: str, received: date | None) -> Advice:
    text = _read_text(path)
    delimiter = ";" if text.split("\n", 1)[0].count(";") > text.split("\n", 1)[0].count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    if len(rows) < 2 or not rows[0] or rows[0][0].strip() != "payment_ref":
        raise AdviceError("no payment_ref header")
    meta = dict(zip(rows[0][0::2], rows[0][1::2], strict=False))
    lines, total = _table_lines(rows[1:])
    return Advice(rel, "csv", _clean(meta.get("payment_ref")), parse_date(meta.get("payment_date")),
                  _clean(meta.get("currency")), total, lines)


def _parse_xlsx(path: Path, rel: str, received: date | None) -> Advice:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as err:  # corrupt zip, bad xml: whatever the library raises, the file is the problem
        raise AdviceError(f"unreadable xlsx: {err}") from err
    try:
        rows = [list(r) for r in workbook.worksheets[0].iter_rows(values_only=True)]
    finally:
        workbook.close()
    if len(rows) < 4 or str(rows[1][0] or "").strip().lower() != "payment advice":
        raise AdviceError("no 'Payment advice' header row")
    lines, total = _table_lines(rows[2:])
    return Advice(rel, "xlsx", _clean(rows[1][1]), None, None, total, lines, payer=_clean(rows[0][0]))


# --- txt (an e-mail) -----------------------------------------------------------------------------------------------

TXT_TOTAL = re.compile(r"(\d[\d.,]*)\s+([A-Z]{3})\b(?:\s+[^\W\d]+){0,2}\s+(\d{1,2}/\d{1,2}/\d{4})")
TXT_LINE = re.compile(
    r"^\s+(\S+)\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+(-?\d[\d.,]*)(?:\s+(-?\d[\d.,]*)\s+(\S.*?))?\s*$")


def _parse_txt(path: Path, rel: str, received: date | None) -> Advice:
    head, _, body = _read_text(path).partition("\n\n")
    subject = re.search(r"^Subject:\s*(.+?)\s*$", head, re.M)
    sent = re.search(r"^Date:\s*(.+?)\s*$", head, re.M)
    if not subject or not sent or not body:
        raise AdviceError("not an e-mail with subject and date")
    when = email.utils.parsedate_to_datetime(sent[1]).date() if email.utils.parsedate(sent[1]) else received
    total = TXT_TOTAL.search(body)
    if not total:
        raise AdviceError("no payment total")
    lines: list[AdviceLine] = []
    for raw in body.splitlines():
        match = TXT_LINE.match(raw)
        if not match:
            continue
        amount = money(match[3])
        deduction = money(match[4]) if match[4] else 0
        lines.append(AdviceLine(len(lines) + 1, match[1], parse_date(match[2]), amount, deduction,
                                match[5], amount + deduction))
    if not lines:
        raise AdviceError("no document lines")
    return Advice(rel, "txt", subject[1].split()[-1], parse_date(total[3], near=when), total[2], money(total[1]),
                  lines)


# --- pdf -----------------------------------------------------------------------------------------------------------

PDF_DATE = re.compile(r"\d{1,2}/\d{1,2}/\d{4}")
PDF_DEDUCTION = re.compile(r"^(-?\d[\d.,]*)\s+(\S.*)$")


PDF_LABELS = {"ref": ("Payment ref.", "Ref."), "amount": ("Amount", "Importe"), "last": ("Paid", "Pagado")}


def _parse_pdf(path: Path, rel: str, received: date | None) -> Advice:
    from pypdf import PdfReader

    try:
        text = "\n".join(page.extract_text() for page in PdfReader(path).pages)
    except Exception as err:  # corrupt or truncated pdf
        raise AdviceError(f"unreadable pdf: {err}") from err
    rows = [r.strip() for r in text.splitlines() if r.strip()]
    label = {key: next((w for w in words if w in rows), None) for key, words in PDF_LABELS.items()}
    if None in label.values():
        raise AdviceError("no remittance table")
    after = lambda key: rows[rows.index(label[key]) + 1]  # noqa: E731
    amount = re.fullmatch(r"(-?\d[\d.,]*)\s+([A-Z]{3})", after("amount"))
    table = rows[rows.index(label["last"]) + 1:]
    footer = next((i for i, r in enumerate(table) if r.startswith("Documento sint")), len(table))
    table = table[:footer]
    starts = [i - 1 for i, r in enumerate(table) if PDF_DATE.fullmatch(r) and i > 0]
    lines: list[AdviceLine] = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(table)
        number, doc_date, *cells = table[start:end]
        if len(cells) < 2:
            raise AdviceError(f"incomplete row for {number}")
        gross, paid = money(cells[0]), money(cells[-1])
        deduction, reason = 0, None
        if len(cells) > 2:
            part = PDF_DEDUCTION.match(" ".join(cells[1:-1]))
            if not part:
                raise AdviceError(f"unreadable deduction for {number}")
            deduction, reason = money(part[1]), part[2]
        lines.append(AdviceLine(len(lines) + 1, number, parse_date(doc_date), gross, deduction, reason, paid))
    if not lines:
        raise AdviceError("no document lines")
    return Advice(rel, "pdf", after("ref"), None, amount[2] if amount else None,
                  money(amount[1]) if amount else None, lines)


# --- layouts nobody has seen, txt and pdf -----------------------------------------------------------------------

_CELL_SPLIT = re.compile(r"\s*[;|\t]\s*| {2,}")
_DATE_CELL = re.compile(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2}")
_PRINTED_AMOUNT = re.compile(r"-?\d[\d.,' ]*[.,]\d{2}(?!\d)")
_CURRENCY = re.compile(r"\b[A-Z]{3}\b")
MAX_CELLS_BEFORE_DATE = 3  # how far into a line its date may be
_MIN_REF_DIGITS = 4


def _date_cell(cell: str) -> str | None:
    if not _DATE_CELL.fullmatch(cell):
        return None
    try:
        return parse_date(cell if cell[:4].isdigit() else re.sub(r"[.-]", "/", cell))
    except AdviceError:
        return None


def _amount_cell(cell: str) -> int | None:
    try:
        return money(cell) if _PRINTED_AMOUNT.fullmatch(cell) else None
    except AdviceError:
        return None


def _is_number_cell(cell: str) -> bool:
    return " " not in cell and any(c.isdigit() for c in cell) and not _date_cell(cell) and _amount_cell(cell) is None


def _rows_of(cells: list[str], offset: int) -> tuple[list[list[str]], list[str]] | None:
    """Lines of the table: each with one date, a document and an amount. What is outside is the head and the foot."""
    starts = [i - offset for i, c in enumerate(cells) if _date_cell(c) and i >= offset]
    pieces = [cells[a:b] for a, b in zip(starts, [*starts[1:], len(cells)], strict=True)]
    while pieces and not _a_line(pieces[0]):
        starts, pieces = starts[1:], pieces[1:]
    if not pieces:
        return None
    foot: list[str] = []
    seen_amount = False
    for at, cell in enumerate(pieces[-1]):  # the last line runs into the foot: nothing after a word that ends it
        if _amount_cell(cell) is not None:
            seen_amount = True
        elif seen_amount and not _date_cell(cell) and not _is_number_cell(cell):
            foot = pieces[-1][at + 1:] + foot
            pieces[-1] = pieces[-1][:at + 1]
            break
    if not all(_a_line(p) for p in pieces):
        return None
    return pieces, cells[:starts[0]] + foot


def _a_line(cells: list[str]) -> bool:
    return ((_date_cell(cells[0]) is not None or _is_number_cell(cells[0])) and sum(
        1 for c in cells if _date_cell(c)) == 1 and any(_is_number_cell(c) for c in cells)
            and any(_amount_cell(c) is not None for c in cells))


def _number_position(rows: list[list[str]]) -> int | None:
    """Which number of the line is ours: the only one, or the only one that always carries the year of its date."""
    numbers = [[c for c in row if _is_number_cell(c)] for row in rows]
    most = max(len(n) for n in numbers)
    if most == 1:
        return 0
    years = [next(_date_cell(c) for c in row if _date_cell(c))[2:4] for row in rows]
    fit = [p for p in range(most) if all(len(n) > p and year in n[p] for n, year in zip(numbers, years, strict=True))]
    return fit[0] if len(fit) == 1 else None


def _paid_ways(amounts: list[int]) -> dict[str, tuple[int, int]]:
    """(gross, paid) of a line under each way a table can print them."""
    biggest = max(amounts, key=abs)
    ways = {"last": (biggest, amounts[-1]), "first": (biggest, amounts[0])}
    if len(amounts) == 2 and abs(amounts[1]) < abs(amounts[0]):
        ways["net"] = (amounts[0], amounts[0] - abs(amounts[1]) if amounts[0] > 0 else amounts[0] + abs(amounts[1]))
    return ways


def _lines_of(rows: list[list[str]], total_of: set[int]) -> tuple[list[AdviceLine], int] | None:
    """The one reading of the amounts whose paid column adds up to a total the document prints."""
    position = _number_position(rows)
    if position is None:
        return None
    amounts = [[a for c in row if (a := _amount_cell(c)) is not None] for row in rows]
    readings: dict[tuple, int] = {}
    for way in ("last", "first", "net"):
        if way == "net" and (any(len(a) > 2 for a in amounts) or not any("net" in _paid_ways(a) for a in amounts)):
            continue
        reading = tuple(_paid_ways(a).get(way, (a[0], a[0])) for a in amounts)
        total = sum(paid for _, paid in reading)
        if total in total_of:
            readings[reading] = total
    if not readings and len(total_of) == 1 and all(len(a) == 1 for a in amounts):
        # One amount per line and one total printed: the same reading a known layout gets when a discount goes unsaid.
        readings = {tuple((a[0], a[0]) for a in amounts): next(iter(total_of))}
    if len(readings) != 1:
        return None
    (reading, total), = readings.items()
    lines = []
    for n, (row, (gross, paid)) in enumerate(zip(rows, reading, strict=True), 1):
        numbers = [c for c in row if _is_number_cell(c)]
        words = [c for c in row if _amount_cell(c) is None and not _date_cell(c) and not _is_number_cell(c)]
        others = numbers[:position] + numbers[position + 1:]
        lines.append(AdviceLine(n, numbers[position], next(_date_cell(c) for c in row if _date_cell(c)), gross,
                                paid - gross, words[0] if words and gross != paid else None, paid,
                                others[0] if others else None))
    return lines, total


def _payment_ref(outside: list[str]) -> str | None:
    tokens = [(("ref" in cell.lower()), token) for cell in outside for token in re.split(r"[\s:]+", cell)
              if sum(c.isdigit() for c in token) >= _MIN_REF_DIGITS and not _date_cell(token)
              and _amount_cell(token) is None]
    return max(tokens, key=lambda t: (t[0], len(t[1])))[1] if tokens else None


def read_cells(text_lines: list[str], fmt: str, rel: str, received: date | None, ref: str | None = None) -> Advice:
    """An advice in a layout no parser knows, by what its cells hold: a line has a date, a document and amounts, and its
    paid amounts add up to a total printed outside the table. Anything not unequivocal is rejected as unknown."""
    cells = [c.strip() for line in text_lines for c in _CELL_SPLIT.split(line) if c.strip()]
    unknown = AdviceError("unknown layout")
    found = []
    for offset in range(MAX_CELLS_BEFORE_DATE + 1):
        parts = _rows_of(cells, offset)
        if parts is None:
            continue
        rows, outside = parts
        printed = {money(m.strip()) for cell in outside for m in _PRINTED_AMOUNT.findall(cell)}
        read = _lines_of(rows, printed)
        if read:
            found.append((read, outside))
    readings = {tuple((x.document, x.gross_cents, x.paid_cents) for x in read[0]) for read, _ in found}
    if len(readings) != 1:
        raise unknown
    (lines, total), outside = found[0]
    amount_text = next((c for c in outside for m in _PRINTED_AMOUNT.findall(c) if money(m.strip()) == total), "")
    currency = _CURRENCY.search(amount_text)
    return Advice(rel, fmt, ref or _payment_ref(outside), None, currency[0] if currency else None, total, lines)


def _by_content(kind: str, path: Path, rel: str, received: date | None) -> Advice:
    if kind == "pdf":
        from pypdf import PdfReader

        try:
            text = "\n".join(page.extract_text() for page in PdfReader(path).pages)
        except Exception as err:  # corrupt or truncated pdf
            raise AdviceError(f"unreadable pdf: {err}") from err
        return read_cells(text.splitlines(), kind, rel, received)
    head, _, body = _read_text(path).partition("\n\n")
    subject = re.search(r"^Subject:\s*(.+?)\s*$", head, re.M)
    return read_cells(body.splitlines(), kind, rel, received, subject[1].split()[-1] if subject else None)


# --- entry points --------------------------------------------------------------------------------------------------

PARSERS = {"csv": _parse_csv, "txt": _parse_txt, "xlsx": _parse_xlsx, "pdf": _parse_pdf}


def parse_advice(path: Path, rel: str | None = None, received: date | None = None) -> Advice:
    kind = KINDS.get(path.suffix.lower())
    if kind is None:
        raise AdviceError(f"unknown format {path.suffix!r}")
    try:
        try:
            advice = PARSERS[kind](path, rel or path.name, received)
        except AdviceError:
            if kind not in ("txt", "pdf"):
                raise
            advice = _by_content(kind, path, rel or path.name, received)
    except AdviceError:
        raise
    except Exception as err:  # a dirty document must never take the run down
        raise AdviceError(f"{type(err).__name__}: {err}") from err
    if not advice.payment_ref:
        raise AdviceError("no payment reference")
    return advice


def _parse_chunk(chunk: list[tuple[Path, str, date | None]]) -> list[tuple[Advice | None, tuple[str, str] | None]]:
    out = []
    for path, rel, received in chunk:
        try:
            out.append((parse_advice(path, rel, received), None))
        except AdviceError as err:
            out.append((None, (rel, str(err))))
    return out


def parse_advices(files: list[tuple], workers: int | None = None) -> AdviceBatch:
    """Files as (path, relative path[, received date]); in parallel, in the order given."""
    items = [(Path(f[0]), f[1], f[2] if len(f) > 2 else None) for f in files]
    workers = workers or min(MAX_WORKERS, os.cpu_count() or 1)
    batch = AdviceBatch()
    if workers == 1 or len(items) < 2 * workers:
        results = [_parse_chunk(items)]
    else:
        size = max(1, len(items) // (workers * 8))
        chunks = [items[i:i + size] for i in range(0, len(items), size)]
        with ProcessPoolExecutor(workers) as pool:
            results = list(pool.map(_parse_chunk, chunks))
    for chunk in results:
        for advice, failure in chunk:
            if advice:
                batch.advices.append(advice)
            else:
                batch.failures.append(failure)
    return batch


@lru_cache(maxsize=4)
def _parse_folder(folder: str) -> AdviceBatch:
    root = Path(folder)
    index_path = root / "index.csv"
    meta: dict[str, dict] = {}
    if index_path.exists():
        meta = {r["file"]: r for r in pl.read_csv(index_path, infer_schema_length=0).iter_rows(named=True)}
    names = sorted(meta) or sorted(str(p.relative_to(root)) for p in root.glob("*/*") if p.suffix.lower() in KINDS)
    files = [(root / n, f"{FOLDER}/{n}", date.fromisoformat(meta[n]["received_date"]) if n in meta else None)
             for n in names]
    batch = parse_advices(files)
    for advice in batch.advices:
        row = meta.get(advice.path.removeprefix(f"{FOLDER}/"), {})
        advice.entity = row.get("entity") or advice.path.split("/")[1]
        advice.payer = row.get("payer_name") or advice.payer
        advice.received_date = row.get("received_date")
    return batch


def phase_advices(phase) -> AdviceBatch:
    """Every advice of the phase, parsed once per process (the rules and the facts share it)."""
    folder = Path(phase.dir) / FOLDER
    return _parse_folder(str(folder)) if folder.is_dir() else AdviceBatch()


def documents_frame(batch: AdviceBatch) -> pl.DataFrame:
    """facts/documents.parquet (CONTRACT §2.3): one row per line of an advice."""
    from ..output import DOCUMENT_SCHEMA

    rows = [(a, x) for a in batch.advices for x in a.lines]
    return pl.DataFrame({
        "docPath": [a.path for a, _ in rows], "docKind": ["remittanceAdvice"] * len(rows),
        "entity": [a.entity for a, _ in rows], "payerName": [a.payer for a, _ in rows],
        "receivedDate": [a.received_date for a, _ in rows], "paymentRef": [a.payment_ref for a, _ in rows],
        "paymentDate": [a.payment_date for a, _ in rows], "paymentTotalCents": [a.total_cents for a, _ in rows],
        "currency": [a.currency for a, _ in rows], "lineNo": [x.line_no for _, x in rows],
        "documentNumber": [x.document for _, x in rows],
        "documentNumberNorm": [normalize_number(x.document) for _, x in rows],
        "grossCents": [x.gross_cents for _, x in rows], "deductionCents": [x.deduction_cents for _, x in rows],
        "reason": [x.reason for _, x in rows], "paidCents": [x.paid_cents for _, x in rows],
        "customerPo": [x.po for _, x in rows], "voucher": [x.voucher for _, x in rows],
        "clause": [None] * len(rows), "clauseValue": [None] * len(rows), "method": ["parser"] * len(rows),
        "model": [None] * len(rows), "cacheKey": [None] * len(rows),
    }, schema=DOCUMENT_SCHEMA)


def residue(batch: AdviceBatch) -> dict[str, dict[str, int]]:
    """Per format: advices read, advices that close, files that did not parse. What does not close is for the model."""
    out: dict[str, dict[str, int]] = {}
    for advice in batch.advices:
        counts = out.setdefault(advice.fmt, {"read": 0, "closed": 0, "failed": 0})
        counts["read"] += 1
        counts["closed"] += advice.closes
    for path, _ in batch.failures:
        kind = KINDS.get(Path(path).suffix.lower(), "other")
        out.setdefault(kind, {"read": 0, "closed": 0, "failed": 0})["failed"] += 1
    return out
