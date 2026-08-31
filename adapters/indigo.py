"""
IndiGo adapter — first source in the register's "Immediate Next Step" list
(Section 9).

IMPORTANT, checked before writing this file: www.goindigo.in/robots.txt
explicitly disallows automated access to the booking/search flow, e.g.:

    Disallow: /search.html
    Disallow: /book.html
    Disallow: /book/*
    Disallow: /booking/*
    Disallow: /bookings/*
    Disallow: /booking-v1.html
    Disallow: /book-flight.html

IndiGo's fare search results are served from that booking flow. That means
this adapter is EXPECTED to be halted by the base class's robots.txt gate
(`BaseAirfareAdapter.run`) as soon as the search submits and lands on a
`/book/...`-style results URL — and it should be. The code below still
implements the full flow (form fill, results wait, extraction) so that:

  1. the robots.txt block is demonstrated with real evidence (the actual
     results URL reached, saved in the feasibility report) rather than
     assumed from reading the file alone;
  2. the same adapter can be pointed at a source whose robots.txt permits
     the equivalent flow, or re-tested if IndiGo's robots.txt changes.

The CSS/text selectors below are best-effort, written from the public
IndiGo booking-widget structure at the time of writing, and are NOT
verified against a live browser render in this environment (this sandbox's
network egress does not include goindigo.in). Expect to adjust selectors
after a first supervised, headed run — see README "First Run" section.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from adapters.base import BaseAirfareAdapter
from config import SearchConfig
from models import FareObservation

if TYPE_CHECKING:
    from playwright.sync_api import Page

_PRICE_RE = re.compile(r"[\u20b9₹]?\s?([\d,]+(?:\.\d+)?)")


class IndiGoAdapter(BaseAirfareAdapter):
    source_type = "direct_airline"

    @property
    def home_url(self) -> str:
        return f"{self.cfg.base_url}/"

    # ------------------------------------------------------------------

    def fill_search_form(self, page: "Page", search: SearchConfig) -> None:
        # The IndiGo homepage search widget is a single-page-app form.
        # Selector strategy: prefer accessible roles/labels over brittle
        # class names, and fall back to a couple of common alternates.
        page.wait_for_load_state("networkidle")

        if search.trip_type == "one-way":
            self._click_first_available(page, [
                "text=One Way",
                "[data-testid='trip-type-oneway']",
                "label:has-text('One Way')",
            ])

        self._fill_first_available(page, [
            "[data-testid='origin-input']",
            "input[placeholder*='From' i]",
            "#fromCity",
        ], search.origin)

        self._fill_first_available(page, [
            "[data-testid='destination-input']",
            "input[placeholder*='To' i]",
            "#toCity",
        ], search.destination)

        self._click_first_available(page, [
            f"li:has-text('{search.travel_date.strftime('%d')}')",
            "[data-testid='departure-date']",
        ])

        self._click_first_available(page, [
            "button:has-text('Search')",
            "[data-testid='search-flights-btn']",
            "button[type='submit']",
        ])

    def wait_for_results(self, page: "Page") -> None:
        page.wait_for_load_state("networkidle")
        # Give the SPA a moment to route into the results/booking view.
        page.wait_for_timeout(2000)

    def extract_fares(self, page: "Page", search: SearchConfig) -> list[FareObservation]:
        """Best-effort structured extraction. Returns an empty list (rather
        than raising) if the expected DOM shape isn't found — a failed
        extraction is itself a valid, documentable feasibility finding."""
        observations: list[FareObservation] = []
        collection_ts = __import__("datetime").datetime.now().isoformat()

        try:
            cards = page.query_selector_all("[data-testid='flight-card'], .flight-card, .fare-card")
        except Exception:
            cards = []

        for card in cards:
            try:
                text = card.inner_text()
            except Exception:
                continue

            flight_no_match = re.search(r"\b6E\s?-?\d{3,4}\b", text)
            times = re.findall(r"\b\d{1,2}:\d{2}\s?(?:AM|PM)?\b", text, flags=re.IGNORECASE)
            price_match = _PRICE_RE.search(text)

            observations.append(FareObservation(
                source=self.cfg.source_name,
                source_type=self.source_type,
                origin=search.origin,
                destination=search.destination,
                travel_date=search.travel_date.isoformat(),
                collection_timestamp=collection_ts,
                airline="IndiGo",
                flight_number=flight_no_match.group(0) if flight_no_match else None,
                departure_time=times[0] if len(times) > 0 else None,
                arrival_time=times[1] if len(times) > 1 else None,
                total_fare=float(price_match.group(1).replace(",", "")) if price_match else None,
                currency="INR" if price_match else None,
                availability_state="available" if price_match else "unknown",
                raw_fragment=text[:500],
            ))

        return observations

    # ------------------------------------------------------------------

    @staticmethod
    def _click_first_available(page: "Page", selectors: list[str], timeout_ms: int = 4000) -> bool:
        for sel in selectors:
            try:
                page.click(sel, timeout=timeout_ms)
                return True
            except Exception:
                continue
        return False

    @staticmethod
    def _fill_first_available(page: "Page", selectors: list[str], value: str, timeout_ms: int = 4000) -> bool:
        for sel in selectors:
            try:
                page.fill(sel, value, timeout=timeout_ms)
                return True
            except Exception:
                continue
        return False
