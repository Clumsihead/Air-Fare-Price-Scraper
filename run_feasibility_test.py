#!/usr/bin/env python3
"""
Run a technical-feasibility test against one source and write a
FeasibilityReport JSON, plus raw HTML / screenshots for anything actually
reached.

Usage:
    python run_feasibility_test.py --source indigo
    python run_feasibility_test.py --source indigo --origin DEL --destination BOM \
        --days-ahead 7 --repeat 3 --headed

This script implements the register's Section 6 "Standard Technical
Validation Protocol" and Section 7 "Validation Matrix" for a single source
per run. Add new sources by writing a new adapters/<name>.py implementing
BaseAirfareAdapter, then registering it in ADAPTERS below.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from adapters.indigo import IndiGoAdapter
from config import RunConfig, SearchConfig

ADAPTERS = {
    "indigo": (IndiGoAdapter, RunConfig(source_name="IndiGo", base_url="https://www.goindigo.in")),
    # Add future sources here, e.g.:
    # "airindia": (AirIndiaAdapter, RunConfig(source_name="AirIndia", base_url="https://www.airindia.com")),
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", required=True, choices=sorted(ADAPTERS.keys()))
    p.add_argument("--origin", default="DEL")
    p.add_argument("--destination", default="BOM")
    p.add_argument("--days-ahead", type=int, default=7, help="Advance-purchase window in days")
    p.add_argument("--repeat", type=int, default=1, help="Repeat query count for stability testing")
    p.add_argument("--headed", action="store_true", help="Run browser with a visible window (debugging)")
    p.add_argument("--output-dir", default="output")
    p.add_argument("--contact-email", default=None,
                    help="Set the contact email embedded in the User-Agent string")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    adapter_cls, run_cfg = ADAPTERS[args.source]

    run_cfg = RunConfig(
        source_name=run_cfg.source_name,
        base_url=run_cfg.base_url,
        headless=not args.headed,
        repeat_queries=args.repeat,
        output_dir=Path(args.output_dir),
        user_agent=(
            run_cfg.user_agent if not args.contact_email else
            run_cfg.user_agent.replace("set-your-contact-email-here", args.contact_email)
        ),
    )

    search_cfg = SearchConfig(
        origin=args.origin.upper(),
        destination=args.destination.upper(),
        travel_date=date.today() + timedelta(days=args.days_ahead),
    )

    adapter = adapter_cls(run_cfg)
    report = adapter.run(search_cfg)

    print("\n" + "=" * 70)
    print(f"FEASIBILITY RESULT — {run_cfg.source_name}  ({search_cfg.origin} -> {search_cfg.destination})")
    print("=" * 70)
    print(f"robots.txt status : {report.robots_txt_status}")
    if report.robots_txt_disallowed_paths:
        print(f"disallowed URLs   : {report.robots_txt_disallowed_paths}")
    print(f"suitability       : {report.suitability}")
    print(f"reason            : {report.suitability_reason}")
    print(f"fare rows captured: {len(report.observations)}")
    print(f"repeat-query      : {report.repeat_query_result}")
    print(f"full report       : {run_cfg.reports_dir / (run_cfg.source_name + '_feasibility_report.json')}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
