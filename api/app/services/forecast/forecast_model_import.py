"""Import the ST21 FY forecast model master workbook (one tab per client, one row per person, month blocks).

parse_master(path) -> MasterImport — pure, no DB. Everything is found by header text, so each client tab's
own layout variant is handled (Hours vs Days vs Max Days vs Budgeted Hours, extension-date pairs,
Allocation %, Commission, monthly vs hourly rates). Nothing is written; the result carries a per-tab
report of what mapped and what did not, for the product owner to read before loading.

Mapping:
  dashboard (RunRate)      → business unit, sales owner, delivery owner, billing type per client
  client tab               → one engagement per client × Team/SOW
  resource row             → allocation (+ one more allocation per extension-date pair)
  'Actual' month blocks    → actuals per allocation-month (hours or days, vacation, unplanned, billed)
  'Forecast' month blocks  → the sheet's own forecast (max billing) for reconciliation only
  WorkingDays tab          → locations + holidays
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
import re

from openpyxl import load_workbook

D = Decimal
MONTHS = {m.lower(): i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], start=1)}
BU_LABELS = {"st21": "ST21", "it avalon": "IT Avalon", "retro rabbit": "Retro Rabbit"}
BU_ABBREV = {"ita", "rr", "st 21", "sa"}                 # roll-up rows, never clients
BILLING_TYPE = {"fixed monthly": "msp", "t&m": "time_and_materials", "closed": None}
LOCATION_MAP = {"us": "US", "usa": "US", "onsite": "US", "in pune": "India - Pune", "in - pune": "India - Pune", "pune": "India - Pune",
                "in chennai": "India - Chennai", "in - chennai": "India - Chennai", "chennai": "India - Chennai", "offshore": "India - Pune",
                "india": "India - Pune", "sa": "South Africa", "south africa": "South Africa"}
SKIP_TABS = {"Dashboard (RunRate)", "Dashboard (Projection)", "IT Avalon Actual & Projection", "WorkingDays", "Costing Sheet", "Billing Loss",
             "Replacement Data", "Template(Hours)", "TEMPLATE", "Costco (Prototype)", "Sheet1"}
MODEL_AS_OF = "2026-09"   # the month the current model master is cut to; bump it when a newer cut arrives.
                          # Never reassigned at runtime: as_of is a parameter, so one request can never change another's.
MONTHLY_RATE_THRESHOLD = D("1000")   # a 'Rate' above this is a monthly rate per person, not hourly
DEFAULT_YEAR = 2026                   # month labels without a year ("January") on tabs that never state one
TAB_ALIASES = {"station casinos": "Stations Casino", "caesars": "Caesars Palace (Project)", "caesers entertainment": "Caesars Entertainment (Staffing)",
               "blue shield-vms": "BCBS Ca-VMS", "christus health-vms": "Christus Health", "dreamscape": "Dreamscape (added line)",
               "first citizens": "First Citizens + VMS", "sierra nevada": "Sierra Nevada + VMS", "costco": "Costco Travel", "deloitte": "Deloitte (India)"}
TYPE_COL = {"staffing": "staff_augmentation", "managed services": "time_and_materials"}
SOW_TERM = re.compile(r"(\d{1,2}-[A-Za-z]{3}-\d{2,4})\s*(?:to|-|–)\s*(\d{1,2}-[A-Za-z]{3}-\d{2,4})")
NAME_MODES = {"-overtime": "overtime", "-on call": "on_call", "-oncall": "on_call", "-part time": "part_time", "-pass thru": "pass_through", "-pass through": "pass_through"}
SOW_ID = re.compile(r"(so?w\s*#?\s*\d+|cr\s*#?\s*\d+|czr-\d+|lmtq\d+|vms)", re.I)


@dataclass
class ActualMonth:
    month: str; kind: str            # kind: actual | forecast (per the sheet's block label)
    units: Optional[Decimal]         # hours or days as the tab counts them
    unit_kind: str                   # hours | days
    vacation: Optional[Decimal]; unplanned: Optional[Decimal]
    max_billing: Optional[Decimal]; billed: Optional[Decimal]

@dataclass
class ModelAllocation:
    resource: str; role: Optional[str]; assignment: Optional[str]; location: Optional[str]
    rate: Optional[Decimal]; rate_basis: str                        # hourly | monthly
    allocation_pct: Decimal; start: Optional[date]; end: Optional[date]
    commission: bool; segment: int                                  # 0 = original SOW, 1.. = extensions
    months: list = field(default_factory=list)                      # [ActualMonth]
    notes: list = field(default_factory=list)
    mode: str = "standard"                                          # standard | overtime | on_call | part_time | pass_through (from a name suffix)
    row_key: str = ""                                               # resource, plus ' #n' when the same name appears more than once
                                                                    # on the engagement — the identity a re-import matches on

@dataclass
class ModelEngagement:
    client: str; tab: str; assignment_key: str; business_unit: Optional[str]; billing_type_raw: Optional[str]
    engagement_type: str; sales_owner: Optional[str]; delivery_owner: Optional[str]
    allocations: list = field(default_factory=list)
    closed: bool = False

@dataclass
class TabReport:
    tab: str; client: str; business_unit: Optional[str]; engagement_type: str
    rows_seen: int = 0; people: int = 0; allocations: int = 0; extensions: int = 0; engagements: int = 0
    months: list = field(default_factory=list); actual_months: int = 0
    sheet_billing_by_month: dict = field(default_factory=dict)      # month -> sum of Billing (actual blocks) / Max Billing (forecast)
    issues: list = field(default_factory=list)

@dataclass
class Blocker:
    """Something the workbook does not say, where guessing would be worse than stopping.

    A blank business unit or a blank location does not fail loudly once loaded: the engagement lands
    under a default, the numbers still add up on screen, and only the GM underneath is wrong. So the
    load refuses and names the cells instead."""
    kind: str                         # business_unit | location
    tab: str
    detail: str                       # what is missing, in the workbook's own terms
    rows: list = field(default_factory=list)       # the people affected, by name

    @property
    def fix(self) -> str:
        if self.kind == "business_unit":
            return f"Add '{self.tab}' to the Dashboard (RunRate) tab under its business unit, with sales owner, delivery owner and billing type."
        return f"Fill the Location column on the {self.tab} tab for: " + ", ".join(self.rows[:12]) + (f" and {len(self.rows) - 12} more" if len(self.rows) > 12 else "")


@dataclass
class MasterImport:
    dashboard: dict                   # client -> {bu, sales_owner, delivery_owner, billing_type}
    locations: dict                   # location -> [holiday dates]
    engagements: list = field(default_factory=list)
    reports: list = field(default_factory=list)
    global_issues: list = field(default_factory=list)
    as_of: str = ""                   # actuals were taken through this month; later months are forecast
    blockers: list = field(default_factory=list)   # [Blocker] — facts the workbook must carry before a load is safe


# ----------------------------------------------------------------------------- helpers
def _t(v) -> str: return "" if v is None else str(v).strip()
def _l(v) -> str: return _t(v).lower()
def _dec(v) -> Optional[Decimal]:
    if v is None or _t(v) == "" or _t(v).startswith("#"): return None
    if isinstance(v, (int, float, Decimal)): return D(str(v))
    try: return D(_t(v).replace("$", "").replace(",", "").replace("%", ""))
    except Exception: return None
def _date(v) -> Optional[date]:
    if isinstance(v, datetime): return v.date()
    if isinstance(v, date): return v
    t = _t(v)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y", "%d-%b-%y", "%b %d, %Y"):
        try: return datetime.strptime(t, fmt).date()
        except ValueError: pass
    return None
def _norm_location(v) -> Optional[str]:
    k = _l(v)
    if not k or _date(v): return None
    for key, val in LOCATION_MAP.items():
        if k == key or k.startswith(key): return val
    return None
def _month_key(label, year_hint):
    """'January', "January'26", 'Sep 2026' -> ('2026-01', year)"""
    t = _l(label).replace("’", "'")
    m = re.match(r"([a-z]+)\s*'?\s*(\d{2,4})?", t)
    if not m or m.group(1)[:3] not in {k[:3] for k in MONTHS}: return None, year_hint
    mon = next(v for k, v in MONTHS.items() if k.startswith(m.group(1)[:3]))
    yr = m.group(2)
    if yr: year = int(yr) if len(yr) == 4 else 2000 + int(yr)
    else: year = year_hint
    return f"{year}-{mon:02d}", year


# ----------------------------------------------------------------------------- reading the workbook
# openpyxl's normal mode parses every sheet up front: ~5 s locally for this model, ~25 s on a staging task,
# which is most of an import request. Read-only mode streams instead, and each sheet is materialised once,
# on first touch, into plain tuples. Random access by (row, column) then costs a list index, and the parsing
# below is unchanged — it still asks for ws.cell(row=, column=).value.
class _Cell:
    __slots__ = ("value",)
    def __init__(self, value): self.value = value


_BLANK = _Cell(None)


class _Grid:
    """One worksheet as rows of values, with the slice of the openpyxl API this module uses."""
    def __init__(self, ws):
        self._rows = [r for r in ws.iter_rows(values_only=True)]
        self.sheet_state = getattr(ws, "sheet_state", "visible")
        self.max_row = len(self._rows)
        self.max_column = max((len(r) for r in self._rows), default=0)

    def cell(self, row: int, column: int) -> _Cell:
        if 1 <= row <= self.max_row:
            r = self._rows[row - 1]
            if 1 <= column <= len(r): return _Cell(r[column - 1])
        return _BLANK


class _Book:
    """The workbook, materialising a sheet the first time it is asked for. Tabs we skip are never read."""
    def __init__(self, src):
        self._wb = load_workbook(src, data_only=True, read_only=True)
        self.sheetnames = list(self._wb.sheetnames)
        self._grids: dict = {}

    def __contains__(self, name): return name in self.sheetnames

    def __getitem__(self, name) -> _Grid:
        g = self._grids.get(name)
        if g is None: g = self._grids[name] = _Grid(self._wb[name])
        return g

    def close(self):
        try: self._wb.close()
        except Exception: pass


# ----------------------------------------------------------------------------- dashboard
def _parse_dashboard(wb) -> dict:
    """Client rows only. The sheet repeats 'Client' / 'ST21' / 'ITA' / 'RR' as a roll-up block below the
    grand total; that block is not a client list, so parsing stops at the first 'Total' row and any
    second header block is ignored."""
    out = {}
    if "Dashboard (RunRate)" not in wb.sheetnames: return out
    ws = wb["Dashboard (RunRate)"]; bu = None; seen_header = False
    for r in range(1, ws.max_row + 1):
        name = _t(ws.cell(row=r, column=2).value)
        if not name: continue
        key = _l(name)
        if key == "total": break                                   # the grand total ends the client list
        if key == "client":
            if seen_header: break                                  # a second 'Client' header starts the roll-up block
            seen_header = True; continue
        if key in BU_LABELS: bu = BU_LABELS[key]; continue
        if key in BU_ABBREV or key in ("subtotal", "new clients") or key.startswith("*"): continue
        if bu is None: continue
        out[name] = {"business_unit": bu, "sales_owner": _t(ws.cell(row=r, column=3).value) or None,
                     "delivery_owner": _t(ws.cell(row=r, column=4).value) or None, "billing_type": _t(ws.cell(row=r, column=5).value) or None}
    return out

def _match_dashboard(dash: dict, tab: str) -> Optional[tuple]:
    alias = TAB_ALIASES.get(_l(tab))
    if alias and alias in dash: return alias, dash[alias]
    t = _l(tab).replace("-vms", "").replace("vms", "").strip()
    best = None
    for name, info in dash.items():
        n = _l(name).replace("-vms", "").replace("+ v", "").strip()
        n = re.sub(r"\(.*?\)", "", n).strip()
        if n == t or n.startswith(t[:8]) or t.startswith(n[:8]):
            if best is None or len(n) > len(best[0]): best = (n, name, info)
    return (best[1], best[2]) if best else None


# ----------------------------------------------------------------------------- working days / holidays
def _parse_workingdays(wb) -> dict:
    out = {}
    if "WorkingDays" not in wb.sheetnames: return out
    ws = wb["WorkingDays"]
    # holiday columns: row 3 headers from col I onward in groups of (date, name, blank)
    for c in range(9, ws.max_column + 1):
        head = _t(ws.cell(row=3, column=c).value)
        loc = _norm_location(head)
        if not loc: continue
        dates = []
        for r in range(4, ws.max_row + 1):
            d_ = _date(ws.cell(row=r, column=c).value)
            if d_: dates.append(d_)
        if dates: out[loc] = sorted(set(out.get(loc, [])) | set(dates))   # the 'Location List' column has no dates; never let it blank a list
    return out


# ----------------------------------------------------------------------------- client tab
def _month_blocks(ws, rep: TabReport):
    """Return [(month_key, kind, {field: col})] from rows 1–4."""
    year_hint = None
    cols = [(c, _l(ws.cell(row=3, column=c).value)) for c in range(1, min(ws.max_column, 400) + 1)]
    cols = [(c, x) for c, x in cols if _month_key(x, 2000)[0]]
    labels = [x for _, x in cols]
    if cols:
        v = ws.cell(row=1, column=cols[0][0]).value                 # a year typed above the first month column
        if isinstance(v, (int, float)) and 2000 < v < 2100: year_hint = int(v)
    if year_hint is None:
        # count back from the first label that carries a year ("January'26"), else assume the model's year
        year_hint = DEFAULT_YEAR
        for i, x in enumerate(labels):
            m = re.search(r"'(\d{2})|(\d{4})", x)
            if m:
                y = 2000 + int(m.group(1)) if m.group(1) else int(m.group(2))
                first_mon = _month_key(labels[0], y)[0]; this_mon = _month_key(x, y)[0]
                year_hint = y - (1 if first_mon and this_mon and first_mon > this_mon else 0); break
    starts = []
    for c in range(1, min(ws.max_column, 400) + 1):
        key, year_hint2 = _month_key(ws.cell(row=3, column=c).value, year_hint)
        if key:
            if starts and key <= starts[-1][0]:                       # rolled into a new year without a year suffix
                y, m = map(int, key.split("-")); key = f"{y+1}-{m:02d}"; year_hint2 = y + 1
            year_hint = year_hint2; kind = _l(ws.cell(row=2, column=c).value)
            starts.append((key, "actual" if kind.startswith("actual") else "forecast", c))
    blocks = []
    for i, (key, kind, c0) in enumerate(starts):
        c1 = starts[i + 1][2] - 1 if i + 1 < len(starts) else min(c0 + 7, ws.max_column)
        f = {}
        for c in range(c0, c1 + 1):
            h = _l(ws.cell(row=4, column=c).value)
            if not h: continue
            if "unplanned" in h: f["unplanned"] = c
            elif "vacation" in h: f["vacation"] = c
            elif h.startswith("max billing"): f["max_billing"] = c
            elif h.startswith("billing") or h.startswith("actual billing"): f["billed"] = c
            elif h.startswith("actual hours"): f["actual_units"] = c; f["unit_kind"] = "hours"
            elif h.startswith(("max hours", "budgeted hours", "hours")): f["units"] = c; f["unit_kind"] = "hours"
            elif h.startswith(("max days", "days")): f["units"] = c; f["unit_kind"] = "days"
        blocks.append((key, kind, f))
    rep.months = [b[0] for b in blocks]
    return blocks

def _parse_tab(wb, tab: str, dash: dict, as_of: str) -> tuple:
    ws = wb[tab]
    m = _match_dashboard(dash, tab)
    client = m[0] if m else tab.strip()
    info = m[1] if m else {}
    rep = TabReport(tab, client, info.get("business_unit"), "")
    if not m: rep.issues.append("Client not found on the run-rate dashboard — business unit and owners unknown.")
    blocks = _month_blocks(ws, rep)
    if not blocks: rep.issues.append("No month columns recognised in rows 1–4."); return [], rep
    # fixed columns by header (row 4)
    H = {c: _l(ws.cell(row=4, column=c).value) for c in range(1, blocks[0][2].get("units", blocks[0][2].get("max_billing", 30)))}
    def col(*prefixes):
        for p in prefixes:
            for c, h in H.items():
                if h.startswith(p): return c
        return None
    c_res, c_role, c_team, c_type = col("resource"), col("role"), col("team/sow", "sow & duration", "team", "sow"), col("type")
    c_team2, c_active = col("team") if col("sow & duration") else None, col("active")
    c_loc, c_rate, c_pct, c_comm = col("location"), col("rate"), col("allocation"), col("commission")
    c_start, c_end = col("original sow start", "sow start", "start", "billing start", "emp. start"), col("original sow end", "sow end", "end", "billing end", "emp. end")
    ext = [c for c, h in H.items() if h.startswith("extension start")]
    if c_res is None: rep.issues.append("No 'Resource' column."); return [], rep
    # engagement type
    bt = _l(info.get("billing_type"))
    tab_title = _l(ws.cell(row=2, column=1).value)
    closed = "closed" in tab_title or bt == "closed"
    if closed: rep.issues.append("Marked CLOSED (tab title or dashboard) — will import with status closed.")
    engagements: dict = {}
    no_dates = 0
    for r in range(5, ws.max_row + 1):
        name = _t(ws.cell(row=r, column=c_res).value)
        if not name: continue
        if _l(name) in ("total", "totals"): break
        rep.rows_seen += 1
        mode = next((v for k, v in NAME_MODES.items() if _l(name).endswith(k)), "standard")
        role = _t(ws.cell(row=r, column=c_role).value) if c_role else ""
        if not role and not (c_rate and _dec(ws.cell(row=r, column=c_rate).value)):
            rep.issues.append(f"Row {r} '{name}': no role and no rate — skipped (looks like a note, not a person)."); continue
        team = _t(ws.cell(row=r, column=c_team).value) if c_team else ""
        if not team and c_team2: team = _t(ws.cell(row=r, column=c_team2).value)
        type_raw = _l(ws.cell(row=r, column=c_type).value) if c_type else ""
        etype = ("staff_augmentation" if type_raw == "staffing" or "staffing" in tab_title else None) or BILLING_TYPE.get(bt) or TYPE_COL.get(type_raw) or "time_and_materials"
        rep.engagement_type = etype
        loc_raw = ws.cell(row=r, column=c_loc).value if c_loc else None
        loc = _norm_location(loc_raw)
        notes = []
        if loc is None and mode != "standard":
            base = _l(name).rsplit("-", 1)[0].strip()
            loc = next((x.location for e_ in engagements.values() for x in e_.allocations if _l(x.resource) == base and x.location), None)
        if loc is None:
            notes.append(f"location '{_t(loc_raw) or 'blank'}' not recognised — needs a value" if _t(loc_raw) else "location blank")
        rate = _dec(ws.cell(row=r, column=c_rate).value) if c_rate else None
        basis = "monthly" if rate is not None and rate >= MONTHLY_RATE_THRESHOLD else "hourly"
        pct = _dec(ws.cell(row=r, column=c_pct).value) if c_pct else None
        pct = D("1") if pct is None else (pct / D(100) if pct > 1 else pct)
        comm = _l(ws.cell(row=r, column=c_comm).value).startswith("y") if c_comm else False
        start = _date(ws.cell(row=r, column=c_start).value) if c_start else None
        end = _date(ws.cell(row=r, column=c_end).value) if c_end else None
        if rate is None: notes.append("no rate")
        sow_term = SOW_TERM.search(team or "")
        if sow_term and not start and not end:
            start, end = _date(sow_term.group(1)), _date(sow_term.group(2))
        if c_active and _l(ws.cell(row=r, column=c_active).value) == "n" and not end:
            notes.append("Active? = N with no end date — will be imported as ended on the last month that has actuals")
        # months
        months = []
        for key, kind, f in blocks:
            units = _dec(ws.cell(row=r, column=f["actual_units"]).value) if kind == "actual" and "actual_units" in f else (_dec(ws.cell(row=r, column=f["units"]).value) if "units" in f else None)
            am = ActualMonth(key, kind, units, f.get("unit_kind", "hours"),
                             _dec(ws.cell(row=r, column=f["vacation"]).value) if "vacation" in f else None,
                             _dec(ws.cell(row=r, column=f["unplanned"]).value) if "unplanned" in f else None,
                             _dec(ws.cell(row=r, column=f["max_billing"]).value) if "max_billing" in f else None,
                             _dec(ws.cell(row=r, column=f["billed"]).value) if "billed" in f else None)
            if kind == "actual" and key > as_of: am.kind = kind = "forecast"
            if kind == "forecast" and key <= as_of and (am.billed is not None or (("actual_units" in f) and _dec(ws.cell(row=r, column=f["actual_units"]).value) is not None)):
                am.kind = "actual"; am.units = _dec(ws.cell(row=r, column=f["actual_units"]).value) if "actual_units" in f else am.units
            months.append(am)
            tot = am.billed if am.kind == "actual" else am.max_billing
            if tot: rep.sheet_billing_by_month[key] = rep.sheet_billing_by_month.get(key, D(0)) + tot
        sid = SOW_ID.search(team or "")
        key = sid.group(1).upper().replace(" ", "") if sid else (SOW_TERM.sub("", team).strip(" -") or "(no SOW named)")
        if key == "VMS" or not sid: key = key  # VMS placements share one engagement per client
        eng = engagements.setdefault(key, ModelEngagement(client, tab, key, info.get("business_unit"), info.get("billing_type"), etype, info.get("sales_owner"), info.get("delivery_owner")))
        eng.closed = closed
        # original segment + one allocation per extension pair
        segs = [(start, end)]
        for i, c in enumerate(ext):
            es, ee = _date(ws.cell(row=r, column=c).value), _date(ws.cell(row=r, column=c + 1).value)
            if es or ee: segs.append((es, ee))
        for i, (s_, e_) in enumerate(segs):
            a = ModelAllocation(resource=name, role=role or None, assignment=team or None, location=loc, rate=rate, rate_basis=basis,
                                allocation_pct=pct, start=s_, end=e_, commission=comm, segment=i, months=months if i == 0 else [],
                                notes=list(notes), mode=mode)
            if i > 0:
                prev = eng.allocations[-1]
                if a.start is None and prev.end: a.start = prev.end + timedelta(days=1)
                elif prev.end and a.start and a.start <= prev.end:
                    # the sheet writes an extension as starting on the day the original ends (nine of ten cases),
                    # occasionally earlier. The extension is the newer contract, so it wins from its start date and
                    # the original gives way the day before — no day is billed twice, and no typed date is changed.
                    if prev.start and a.start > prev.start:
                        overlap = (prev.end - a.start).days + 1
                        prev.end = a.start - timedelta(days=1)
                        if overlap > 1: a.notes.append(f"extension {i} starts {overlap} days before the previous segment ended — the previous segment now ends {prev.end}")
                    else:
                        a.notes.append(f"extension {i} starts on or before the previous segment's start ({prev.start}) — check the dates")
                rep.extensions += 1
            eng.allocations.append(a); rep.allocations += 1
        rep.people += 1
        if not start and not end: no_dates += 1
        if notes: rep.issues.append(f"{name}: " + "; ".join(notes))
    rep.actual_months = len({m.month for e in engagements.values() for a in e.allocations for m in a.months if m.kind == "actual"})
    rep.engagements = len(engagements)
    if no_dates: rep.issues.append(f"{no_dates} of {rep.people} people have no start/end dates (row or SOW text) — the month columns decide their window.")
    # identity for re-import: the name, made unique within the engagement. Eleven 'TBC' placeholders on one SOW
    # are eleven seats, and a re-import must find each of them again rather than collapse them into one.
    for eng in engagements.values():
        base_rows = [a for a in eng.allocations if a.segment == 0]
        seen: dict = {}
        total = Counter(a.resource for a in base_rows)
        for a in base_rows:
            n = seen[a.resource] = seen.get(a.resource, 0) + 1
            a.row_key = f"{a.resource} #{n}" if total[a.resource] > 1 else a.resource
        for a in eng.allocations:                                   # extensions share their base row's key
            if a.segment > 0:
                a.row_key = next(b.row_key for b in reversed(base_rows) if b.resource == a.resource)
    return list(engagements.values()), rep


def parse_master(src, as_of: Optional[str] = None) -> MasterImport:
    """as_of: the model's own month ('YYYY-MM'); months after it are never treated as actuals.
    None means MODEL_AS_OF. The value is carried on the result and printed in the report, so what the
    numbers mean is never implicit."""
    as_of = as_of or MODEL_AS_OF
    wb = _Book(src)
    dash = _parse_dashboard(wb)
    out = MasterImport(dash, _parse_workingdays(wb), as_of=as_of)
    if not dash: out.global_issues.append("Run-rate dashboard not found — no business units or owners.")
    for name in wb.sheetnames:
        if name in SKIP_TABS or wb[name].sheet_state != "visible": continue
        try:
            engs, rep = _parse_tab(wb, name, dash, as_of)
        except Exception as e:                                   # one bad tab must not sink the import
            rep = TabReport(name, name, None, ""); rep.issues.append(f"Could not parse this tab: {e!r}"); engs = []
        out.engagements.extend(engs); out.reports.append(rep)
    wb.close()
    out.blockers = _blockers(out)
    on_dash_not_tabs = [c for c in dash if not any(_match_dashboard({c: dash[c]}, r.tab) for r in out.reports)]
    if on_dash_not_tabs:
        out.global_issues.append("On the dashboard but with no client tab (numbers typed in directly): " + ", ".join(on_dash_not_tabs))
    return out


def _blockers(imp: MasterImport) -> list:
    """What must be filled in before a load. Nothing here is a judgement call — each one is a blank cell."""
    out = []
    for rep in imp.reports:
        engs = [e for e in imp.engagements if e.tab == rep.tab]
        if engs and not rep.business_unit:
            out.append(Blocker("business_unit", rep.tab,
                               f"not on the run-rate dashboard, so it has no business unit, sales owner or billing type "
                               f"({len(engs)} {'engagement' if len(engs) == 1 else 'engagements'}, "
                               f"{len({a.resource for e in engs for a in e.allocations})} people)",
                               sorted({e.assignment_key for e in engs})))
        blank = sorted({a.resource for e in engs for a in e.allocations if not a.location})
        if blank:
            out.append(Blocker("location", rep.tab,
                               f"{len(blank)} {'person has' if len(blank) == 1 else 'people have'} no Location, "
                               f"and a blank location is charged US burden and the US floor",
                               blank))
    return out


# ----------------------------------------------------------------------------- loader
from app.services.forecast import ZERO, Actual, Allocation, Calendar, Engagement, compute   # noqa: E402

def _window(me: ModelEngagement):
    """Engagement window = earliest start / latest end on its people, else the span of its month columns."""
    starts = [a.start for a in me.allocations if a.start]; ends = [a.end for a in me.allocations if a.end]
    months = sorted({m.month for a in me.allocations for m in a.months})
    if not months and not (starts and ends): return None, None
    def first_day(k): y, m = map(int, k.split("-")); return date(y, m, 1)
    def last_day(k):
        import calendar as _c; y, m = map(int, k.split("-")); return date(y, m, _c.monthrange(y, m)[1])
    s = min(starts) if starts else first_day(months[0])
    e = max(ends) if ends else last_day(months[-1])
    if months and any(a.end is None for a in me.allocations):
        e = max(e, last_day(months[-1]))            # someone has no end date: the sheet's last month bounds them
    if months and any(a.start is None for a in me.allocations):
        s = min(s, first_day(months[0]))
    return s, e

def _alloc_dates(a: ModelAllocation, eng_start: date, eng_end: date):
    """People without dates: window = first..last month with hours/days (> 0) in the sheet; Active?=N ends at the last actual."""
    active = [m.month for m in a.months if (m.units or ZERO) > 0 or (m.billed or ZERO) > 0]
    import calendar as _c
    s, e = a.start, a.end
    if s is None and active: y, m = map(int, active[0].split("-")); s = date(y, m, 1)
    if e is None and active:
        last_actual = [m for m in active if any(x.month == m and x.kind == "actual" for x in a.months)]
        if any("Active? = N" in n for n in a.notes) and last_actual:
            y, m = map(int, last_actual[-1].split("-")); e = date(y, m, _c.monthrange(y, m)[1])
        else:
            y, m = map(int, active[-1].split("-")); e = date(y, m, _c.monthrange(y, m)[1])
    return (max(s, eng_start) if s else eng_start), (min(e, eng_end) if e else eng_end)

def to_engine(me: ModelEngagement, cal: Calendar, cost_rates: Optional[dict] = None, hours_per_day: Decimal = D("8")):
    """-> (Engagement, [Allocation], [Actual], notes). cost_rates: {(location, role): cost/hour}; absent -> cost unknown."""
    notes = []
    s, e = _window(me)
    if not s or not e: return None, [], [], ["no dates and no month columns — cannot place this engagement in time"]
    etype = me.engagement_type
    eng = Engagement(f"{me.client}:{me.assignment_key}", etype, s, e, None, None, False, False)
    allocs, actuals = [], []
    for i, a in enumerate(me.allocations):
        aid = f"{me.assignment_key}:{a.row_key or a.resource}:{a.segment}"
        a_s, a_e = _alloc_dates(a, s, e)
        if a_e < a_s: notes.append(f"{a.resource}: window ends before it starts ({a_s}..{a_e}) — skipped"); continue
        loc = a.location or "US"
        cost = (cost_rates or {}).get((loc, a.role)) if cost_rates else None
        basis = a.rate_basis
        units_kind = next((m.unit_kind for m in a.months), "hours")
        if basis == "hourly" and units_kind == "days": basis = "daily"
        rate = a.rate
        sheet_rate_is_hourly = a.rate is not None and a.rate < MONTHLY_RATE_THRESHOLD      # before flat-billing rewrites basis
        sheet_rate_per_day = sheet_rate_is_hourly and basis == "daily" and a.rate >= D("400")
        flat = [m.max_billing for m in a.months if m.max_billing]
        if basis != "monthly" and len(flat) >= 3 and len(set(flat)) == 1 and len({m.units for m in a.months if m.units}) > 1 and rate:
            # Max Billing is the same every month while the days/hours vary: this person is billed a flat monthly amount
            # (Costco: 173 h × rate every month). Import as a monthly rate so the forecast matches the contract, not the calendar.
            basis, rate = "monthly", flat[0] / (a.allocation_pct or D(1))
            notes.append(f"{a.resource}: billed flat {flat[0]}/month ({flat[0] / a.rate:.0f} h × {a.rate}) — imported as a monthly rate")
        if basis == "daily" and rate is not None and rate < MONTHLY_RATE_THRESHOLD and rate < D("400"):
            # a Days-based tab with an hourly-sized rate bills rate × 8 per day (Deloitte: 29.92 × 17 d × 8 = 4068.62)
            basis = "hourly"
        util = a.allocation_pct
        if a.mode in ("overtime", "on_call"):
            util = ZERO; notes.append(f"{a.resource}: {a.mode.replace('_', ' ')} line — no planned hours; actuals only")
        elif a.mode == "part_time":
            # plan part-time people at their observed share of a full month
            obs = [(m.units if m.unit_kind == "hours" else (m.units or ZERO) * hours_per_day) for m in a.months if m.kind == "actual" and m.units]
            if obs:
                util = min(D("1"), (sum(obs) / len(obs)) / (D(21) * hours_per_day)).quantize(D("0.01"))
                notes.append(f"{a.resource}: part-time — planned at {util:.0%} of a full month (average of actual hours)")
        elif a.mode == "pass_through":
            notes.append(f"{a.resource}: pass-through billing — revenue has no margin; set cost = bill rate")
        allocs.append(Allocation(aid, a.role or a.resource, loc, "w2_employee", cost, a.assignment, util, rate, a_s, a_e, None, basis, a.resource))
        for m in a.months:
            if m.kind != "actual": continue
            hrs = None
            if m.billed is not None and sheet_rate_is_hourly:
                # the invoice is the truth for hours: the sheet's leave columns say 'hours' and hold days (SoundHound),
                # or hold days under an hours header (Costco September), and Costco's Days column is the calendar,
                # not what was billed — 1,606 of 2,705 actual months disagreed with the invoice by the other route
                hrs = m.billed / a.rate * (hours_per_day if sheet_rate_per_day else D(1))
            elif m.units is not None:
                net = m.units - (m.vacation or ZERO) - (m.unplanned or ZERO)
                hrs = net * hours_per_day if m.unit_kind == "days" else net
            if hrs is not None or m.billed is not None:
                actuals.append(Actual(aid, m.month, hrs, m.billed))
    return eng, allocs, actuals, notes

def reconcile(imp: MasterImport, cal: Calendar) -> list:
    """Run the engine on every imported engagement and compare its revenue by month with the sheet's own billing.
    -> [{tab, engagement, months: {month: (engine, sheet)}, status, missing}]"""
    out = []
    for me in imp.engagements:
        eng, allocs, acts, notes = to_engine(me, cal)
        if eng is None: out.append(dict(tab=me.tab, engagement=me.assignment_key, error=notes)); continue
        f = compute(eng, allocs, [], cal, acts)
        sheet = {}
        for a in me.allocations:
            for m in a.months:
                v = m.billed if m.kind == "actual" else m.max_billing
                if v: sheet[m.month] = sheet.get(m.month, ZERO) + v
        out.append(dict(tab=me.tab, engagement=me.assignment_key, people=len(allocs), type=eng.type, status=f.status,
                        months={k: (next((m.revenue for m in f.months if m.month == k), ZERO), sheet.get(k, ZERO)) for k in sorted(set(sheet) | {m.month for m in f.months})},
                        billing_loss=f.billing_loss, actual_revenue=f.actual_revenue, forecast_total=f.total_revenue, notes=notes))
    return out


def _inconsistent_rows(me: ModelEngagement, hours_per_day=D("8")) -> list:
    """People whose sheet Max Billing in forecast months is not rate × units (×8 for days) — the sheet disagrees with itself."""
    out = []
    for a in me.allocations:
        if not a.rate or a.mode != "standard": continue
        for m in a.months:
            if m.kind != "forecast" or not m.max_billing or not m.units: continue
            expect = a.rate * a.allocation_pct if a.rate_basis == "monthly" else a.rate * m.units * (hours_per_day if m.unit_kind == "days" else D(1)) * a.allocation_pct
            if expect and abs(m.max_billing - expect) > expect * D("0.05"):
                out.append(f"{a.resource}: {m.month} Max Billing {m.max_billing:,.0f} but rate {a.rate} × {m.units} {m.unit_kind} = {expect:,.0f}"); break
    return out


def dry_run(imp: MasterImport, cal: Calendar) -> dict:
    """Everything the product owner needs to approve the load: counts by BU, decisions needed, and the engine run against the sheet."""
    bus = {}
    for me in imp.engagements:
        b = bus.setdefault(me.business_unit or "Unassigned", dict(clients=set(), engagements=0, people=0, closed=0, forecast_total=ZERO, actual_total=ZERO, beyond_sow=[], inconsistent=[], notes=[]))
        b["clients"].add(me.client); b["engagements"] += 1; b["people"] += len({a.resource for a in me.allocations}); b["closed"] += me.closed
        eng, allocs, acts, notes = to_engine(me, cal)
        if eng is None: b["notes"].append(f"{me.tab} / {me.assignment_key}: " + "; ".join(notes)); continue
        f = compute(eng, allocs, [], cal, acts)
        b["forecast_total"] += f.total_revenue; b["actual_total"] += f.actual_revenue
        b["notes"] += [f"{me.tab}: {n}" for n in notes]
        # people with an explicit end date whom the sheet keeps billing after it
        after = sorted({m.month for a in me.allocations if a.end for m in a.months if m.kind == "forecast" and m.max_billing and m.month > a.end.strftime("%Y-%m")})
        if after:
            who = sorted({a.resource for a in me.allocations if a.end for m in a.months if m.kind == "forecast" and m.max_billing and m.month > a.end.strftime("%Y-%m")})
            b["beyond_sow"].append(f"{me.tab} / {me.assignment_key}: {len(who)} people billed in the sheet after their end date, through {after[-1]} (e.g. {who[0]} ends {next(a.end for a in me.allocations if a.resource == who[0] and a.end)})")
        b["inconsistent"] += [f"{me.tab}: {x}" for x in _inconsistent_rows(me)]
    return dict(bus=bus, reports=imp.reports, global_issues=imp.global_issues, locations={k: len(v) for k, v in imp.locations.items()})


def dry_run_markdown(imp: MasterImport, cal: Optional[Calendar] = None) -> str:
    cal = cal or Calendar(D("8"), D("0.35"), {}, {}, {k: set(v) for k, v in imp.locations.items()})
    d = dry_run(imp, cal)
    L = ["# Forecast model import — dry run", "", "Nothing has been loaded. This is what the importer read from the workbook and what the DealGate engine makes of it.", ""]
    if imp.blockers:
        L += ["> **This workbook cannot be loaded yet.** The cells below are blank, and every default the tool could pick "
              "would be wrong in a way the totals would still hide. Fill them in and upload again.", ""]
        for b in imp.blockers:
            L.append(f"- **{b.tab}** — {b.detail}. {b.fix}")
        L.append("")
    L.append(f"**Actuals are taken through {imp.as_of}; every later month is forecast.** "
             f"If that is not the month this workbook is cut to, re-run with the right as-of before loading.")
    L.append("")
    L.append(f"Dashboard clients: {len(imp.dashboard)} · client tabs parsed: {len(imp.reports)} · engagements: {len(imp.engagements)} · holidays loaded for: " + ", ".join(f"{k} ({v})" for k, v in d["locations"].items()))
    for g in d["global_issues"]: L.append(f"- ⚠ {g}")
    L += ["", "## By business unit", "", "| BU | Clients | Engagements | People | Closed | Engine forecast (term) | Actuals captured |", "|---|---|---|---|---|---|---|"]
    for bu, b in d["bus"].items():
        L.append(f"| {bu} | {len(b['clients'])} | {b['engagements']} | {b['people']} | {b['closed']} | {b['forecast_total']:,.0f} | {b['actual_total']:,.0f} |")
    L += ["", "## Tabs", "", "| Tab | Client (dashboard) | BU | Type | Engagements | People | Allocations (ext.) | Months (with actuals) | Issues |", "|---|---|---|---|---|---|---|---|---|"]
    for r in imp.reports:
        L.append(f"| {r.tab} | {r.client} | {r.business_unit or '—'} | {r.engagement_type or '—'} | {r.engagements} | {r.people} | {r.allocations} ({r.extensions}) | {len(r.months)} ({r.actual_months}) | {len(r.issues)} |")
    L += ["", "## Where the sheet forecasts past the SOW end", "", "DealGate forecasts to the contract end and shows the roll-off; the sheet assumes renewal. Extend these in the tool when renewed, or they drop out of the forecast after the SOW end.", ""]
    for bu, b in d["bus"].items(): L += [f"- {x}" for x in b["beyond_sow"]]
    L += ["", "## Rows where the sheet disagrees with itself", "", "Max Billing in a forecast month is not rate × hours/days. The engine uses the rate; fix the sheet row or the rate in the tool.", ""]
    for bu, b in d["bus"].items(): L += [f"- {x}" for x in b["inconsistent"]]
    L += ["", "## Assumed, because the workbook does not say", "",
          "- **Employment type**: the model has no W-2 / 1099 column, so every person imports as W-2. For US people that is 36% burden; a 1099 contractor is 5%. Fix contractors on the Allocations tab before reading a US margin.",
          "- **'Offshore' / 'Onsite'**: Offshore is imported as India - Pune, Onsite as US. Pune and Chennai share burden and floor; only the holiday list differs.",
          "- **Cost per hour**: the Costing Sheet is empty, so every person is *cost unknown* and the engagement shows INCOMPLETE until the rate card or a cost per hour covers them.",
          "- **Currency**: every figure is taken as USD, including Retro Rabbit.",
          "- **Actual hours** are taken from the invoice (billed ÷ hourly rate) where the sheet has one; the Days / Vacation columns are not consistent enough to use.", ""]
    L += ["", "## How special rows were imported", ""]
    for bu, b in d["bus"].items():
        flat = [n for n in b["notes"] if "flat" in n]; other = [n for n in b["notes"] if "flat" not in n]
        if flat: L.append(f"- {bu}: {len(flat)} people billed a flat monthly amount (Max Billing constant) — imported as monthly rates, e.g. {flat[0]}")
        L += [f"- {bu}: {n}" for n in other]
    L += ["", "## Issues by tab", ""]
    for r in imp.reports:
        if r.issues:
            L.append(f"**{r.tab}**"); L += [f"- {i}" for i in r.issues[:30]]
            if len(r.issues) > 30: L.append(f"- … {len(r.issues)-30} more")
            L.append("")
    return "\n".join(L)
