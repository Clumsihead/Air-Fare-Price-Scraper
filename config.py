"""
Shared configuration objects for the airfare feasibility scraper.

Keeping the search parameters and run settings in one typed place means
every adapter (IndiGo today, other airlines/OTAs later) consumes the same
shape of input, per the SIH Airfare Source Validation Register's
"Standard Technical Validation Protocol" (Section 6).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path


@dataclass(frozen=True)
class SearchConfig:
    """One test itinerary, matching the register's standard protocol."""

    origin: str = "DEL"
    destination: str = "BOM"
    trip_type: str = "one-way"          # register mandates one-way for the pilot test
    adults: int = 1
    children: int = 0
    infants: int = 0
    cabin: str = "economy"
    travel_date: date = field(default_factory=lambda: date.today() + timedelta(days=7))

    def advance_purchase_days(self, observation_date: date | None = None) -> int:
        obs = observation_date or date.today()
        return (self.travel_date - obs).days


@dataclass(frozen=True)
class RunConfig:
    """Operational / ethics settings for a single feasibility run."""

    source_name: str = "IndiGo"
    base_url: str = "https://www.goindigo.in"
    user_agent: str = (
        "SIH-AirfareIndex-FeasibilityBot/0.1 "
        "(+research project; contact: set-your-contact-email-here; "
        "respects robots.txt; no auth/CAPTCHA bypass)"
    )
    # Hard ethical gates — do not flip these to force scraping through a block.
    respect_robots_txt: bool = True
    attempt_captcha_bypass: bool = False
    attempt_auth_bypass: bool = False
    attempt_antibot_bypass: bool = False

    headless: bool = True
    navigation_timeout_ms: int = 30_000
    action_timeout_ms: int = 15_000
    slow_mo_ms: int = 0
    repeat_queries: int = 1              # register: "repeat sufficiently to assess stability"
    request_delay_seconds: float = 3.0   # be a polite, low-rate visitor

    output_dir: Path = Path("output")

    @property
    def raw_html_dir(self) -> Path:
        return self.output_dir / "raw_html"

    @property
    def screenshots_dir(self) -> Path:
        return self.output_dir / "screenshots"

    @property
    def json_dir(self) -> Path:
        return self.output_dir / "json"

    @property
    def reports_dir(self) -> Path:
        return self.output_dir / "reports"

    def ensure_dirs(self) -> None:
        for d in (self.raw_html_dir, self.screenshots_dir, self.json_dir, self.reports_dir):
            d.mkdir(parents=True, exist_ok=True)
