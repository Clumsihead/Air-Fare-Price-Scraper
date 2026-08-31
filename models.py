"""
Shared result models.

FareObservation mirrors the "Validation Matrix" template in the register
(Section 7): one row per captured flight/fare, with explicit fields for
whether each element was actually captured (rather than silently omitted).

FeasibilityReport is the top-level artifact this tool exists to produce:
a documented, evidence-backed answer to "can we programmatically and
reliably collect fares from this source, within its access rules?"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class FareObservation:
    source: str
    source_type: str                 # direct_airline / ota / metasearch / api
    origin: str
    destination: str
    travel_date: str
    collection_timestamp: str
    airline: Optional[str] = None
    flight_number: Optional[str] = None
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    fare_class_or_brand: Optional[str] = None
    base_fare: Optional[float] = None
    taxes: Optional[float] = None
    fees: Optional[float] = None
    total_fare: Optional[float] = None
    currency: Optional[str] = None
    availability_state: str = "unknown"   # available / sold_out / cancelled / unknown
    raw_fragment: Optional[str] = None    # verbatim text node the value was parsed from, for audit


@dataclass
class StepLog:
    """One entry in the run's audit trail — what we did, and what happened."""
    step: str
    status: str            # ok / blocked / error / skipped
    detail: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class FeasibilityReport:
    source: str
    source_type: str
    test_route: str
    trip_type: str
    run_started_at: str
    run_finished_at: Optional[str] = None

    # Section 7 validation-matrix fields
    active: str = "uncertain"                 # Yes/No/Uncertain
    domestic_fares: str = "uncertain"
    public_access: str = "uncertain"           # Yes/No/Partial
    login_required: str = "uncertain"          # No/Optional/Required
    js_dependency: str = "uncertain"           # Low/Medium/High
    browser_automation: str = "playwright"
    structured_data: str = "uncertain"         # HTML/JSON/embedded/unknown
    repeat_query_result: str = "not_tested"    # Stable/Variable/Fails/not_tested
    anti_bot_observed: str = "none_observed"
    robots_txt_status: str = "not_checked"
    robots_txt_disallowed_paths: list[str] = field(default_factory=list)
    source_provenance: str = "direct"

    suitability: str = "NOT SUITABLE"          # HIGH/MEDIUM/LOW/NOT SUITABLE
    suitability_reason: str = ""

    fields_captured: dict[str, bool] = field(default_factory=dict)
    observations: list[FareObservation] = field(default_factory=list)
    steps: list[StepLog] = field(default_factory=list)
    artifacts: dict[str, list[str]] = field(default_factory=lambda: {
        "raw_html": [], "screenshots": [], "json": []
    })
    notes: list[str] = field(default_factory=list)

    def log(self, step: str, status: str, detail: str = "") -> None:
        self.steps.append(StepLog(step=step, status=status, detail=detail))

    def finish(self) -> None:
        self.run_finished_at = datetime.now().isoformat()
