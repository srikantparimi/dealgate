#!/usr/bin/env python3
"""Load the FY forecast model master (.xlsx) into DealGate without the browser.

Three modes, all against the same proven path (POST /api/engagements/import-forecast-model):

  --offline            parse the file here and write the dry-run report. No server, no auth, nothing created.
  (default)            dry run on the server: the report comes back, nothing is created.
  --load               dry run, show the counts, ask once, then create.

The workbook holds real staff names and rates: it is never committed, and the report is written
outside the repo (default /tmp). Nothing in this script prints a rate or a person's pay.

  python scripts/load_forecast_model.py --file ~/ST21_FY2526_Forecast_Model_Master.xlsx --offline
  DEALGATE_TOKEN=... python scripts/load_forecast_model.py --file ~/model.xlsx --base-url https://app.dealgateapp.com
  DEALGATE_TOKEN=... python scripts/load_forecast_model.py --file ~/model.xlsx --base-url https://app.dealgateapp.com --load
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

PATH = "/api/engagements/import-forecast-model"


def _report_path(args) -> Path:
    p = Path(args.report or (Path(args.out_dir) / f"forecast-model-dryrun-{date.today():%Y%m%d}.md"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def offline(args) -> int:
    """Parse with the same importer the API uses, and write the report. Needs only openpyxl."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
    from decimal import Decimal as D

    from app.services.forecast import Calendar
    from app.services.forecast.forecast_model_import import dry_run_markdown, parse_master

    imp = parse_master(args.file, as_of=args.as_of)   # None -> the importer's MODEL_AS_OF
    cal = Calendar(D("8"), D("0.35"), {}, {}, {k: set(v) for k, v in imp.locations.items()})
    md = dry_run_markdown(imp, cal)
    out = _report_path(args)
    out.write_text(md)
    print(f"Parsed locally. {len(imp.reports)} client tabs → {len(imp.engagements)} engagements, "
          f"{sum(r.people for r in imp.reports)} people. Nothing was created.")
    print(f"Report: {out}")
    return 0


def _post(args, dry_run: bool) -> dict:
    import requests

    token = args.token or os.environ.get("DEALGATE_TOKEN")
    if not token:
        sys.exit("No token. Set DEALGATE_TOKEN (the same bearer the e2e suite uses) or pass --token.")
    url = args.base_url.rstrip("/") + PATH
    with open(args.file, "rb") as fh:
        r = requests.post(url, headers={"Authorization": f"Bearer {token}"},
                          files={"file": (Path(args.file).name, fh,
                                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                          data={"dry_run": str(dry_run).lower(), **({"as_of": args.as_of} if args.as_of else {})},
                          timeout=args.timeout)
    if r.status_code == 422:
        detail = r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else None
        blockers = (detail or {}).get("blockers") if isinstance(detail, dict) else None
        if blockers:
            print(f"Not loaded — fix these in the workbook first ({len(blockers)}):")
            for b in blockers:
                print(f"  - {b.get('tab')}: {b.get('detail')}")
                print(f"    {b.get('fix')}")
            sys.exit(2)
        sys.exit(f"The server would not read that file: {detail or r.text[:400]}")
    if r.status_code == 401 or r.status_code == 403:
        sys.exit("Token rejected. Get a fresh one the way the e2e suite does.")
    r.raise_for_status()
    return r.json()


def _summarise(body: dict) -> None:
    for b in body.get("blockers", []):
        print(f"  BLOCKER {b.get('tab')}: {b.get('detail')}")
        print(f"          {b.get('fix')}")
    for g in body.get("by_business_unit", []):
        print(f"  {g.get('business_unit') or 'not on the dashboard':16} "
              f"{g.get('clients', 0):>3} clients · {g.get('engagements', 0):>3} engagements · "
              f"{g.get('people', 0):>4} people · {g.get('closed', 0)} closed")
    noisy = [t for t in body.get("tabs", []) if t.get("issues")]
    if noisy:
        print(f"  {len(noisy)} tabs have something to look at — see the report.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True, help="the forecast model master .xlsx (never committed)")
    ap.add_argument("--base-url", default=os.environ.get("DEALGATE_URL", ""), help="e.g. https://app.dealgateapp.com")
    ap.add_argument("--token", help="bearer token; or set DEALGATE_TOKEN")
    ap.add_argument("--as-of", help="the month this workbook is cut to, YYYY-MM; later months are never actuals. "
                                    "Left out, the server and the importer use their own MODEL_AS_OF — never today's date, "
                                    "which would import an unbilled month as actuals.")
    ap.add_argument("--offline", action="store_true", help="parse here, no server")
    ap.add_argument("--load", action="store_true", help="create the rows after the dry run (asks once)")
    ap.add_argument("--yes", action="store_true", help="skip the question (for a scripted run)")
    ap.add_argument("--out-dir", default="/tmp", help="where the report is written (outside the repo)")
    ap.add_argument("--report", help="exact path for the report")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    if not Path(args.file).is_file():
        sys.exit(f"No such file: {args.file}")
    if args.offline:
        return offline(args)
    if not args.base_url:
        sys.exit("Pass --base-url (or set DEALGATE_URL), or use --offline.")

    print(f"Dry run against {args.base_url} — nothing is created.")
    body = _post(args, dry_run=True)
    out = _report_path(args)
    out.write_text(body.get("report_markdown", ""))
    _summarise(body)
    print(f"Report: {out}")
    if not args.load:
        print("Read the report, then run again with --load to create the rows.")
        return 0

    tabs = body.get("tabs", [])
    bus = body.get("by_business_unit", [])
    people = sum(g.get("people", 0) for g in bus) or sum(t.get("people", 0) for t in tabs)
    if not args.yes:
        print(f"\nThis will create {people} people across {len(tabs)} client tabs on {args.base_url},")
        print("add the model's locations to Settings with placeholder burden and floors,")
        print("and load actuals. Re-running the same file updates rather than duplicates.")
        if input("Type 'load' to go ahead: ").strip().lower() != "load":
            print("Nothing was created.")
            return 1
    created = _post(args, dry_run=False).get("created") or {}
    if created:
        print("Loaded: " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in created.items()))
    else:
        print("Loaded.")
    print(f"Open {args.base_url}/portfolio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
