"""
Offline, network-free test of RobotsGate against a captured snapshot of
IndiGo's real robots.txt (fetched 2026-08-30 from https://www.goindigo.in/robots.txt,
trimmed to the rules relevant to the booking/search flow — full snapshot is
also written by run_feasibility_test.py into output/reports/ on every real run).

Run with:  python -m tests.test_robots_gate   (from the project root)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robots_checker import RobotsGate  # noqa: E402

FIXTURE = Path(__file__).parent / "fixture_indigo_robots_trimmed.txt"


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
    def raise_for_status(self):
        pass


def main() -> int:
    fixture_text = FIXTURE.read_text()

    with patch("robots_checker.requests.get", return_value=_FakeResponse(fixture_text)):
        gate = RobotsGate("https://www.goindigo.in", "SIH-AirfareIndex-FeasibilityBot/0.1")

        cases = {
            "https://www.goindigo.in/": True,
            "https://www.goindigo.in/about-us.html": True,
            "https://www.goindigo.in/search.html": False,
            "https://www.goindigo.in/book/flight-select.html": False,
            "https://www.goindigo.in/content/indigo/in/en/booking/review.html": False,
            "https://www.goindigo.in/bookings/summary": False,
        }

        failures = []
        for url, expected in cases.items():
            decision = gate.is_allowed(url)
            status = "PASS" if decision.allowed == expected else "FAIL"
            print(f"[{status}] {url:65s} expected={expected!s:5s} got={decision.allowed}")
            if status == "FAIL":
                failures.append(url)

    if failures:
        print(f"\n{len(failures)} case(s) failed: {failures}")
        return 1
    print("\nAll robots-gate cases passed — booking/search flow is correctly detected as disallowed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
