"""
Abstract adapter contract.

Every source-specific adapter (IndiGo today; MakeMyTrip, Air India, etc.
later, per the register's Tier A/B list) implements this interface. The
orchestration logic — robots.txt gating, screenshotting, raw HTML capture,
repeat-query stability testing, and feasibility-report assembly — lives
once in `run()` here, so adding a new source means writing only the
source-specific `fill_search_form` / `wait_for_results` / `extract_fares`
methods.

Ethical gates are enforced in this base class, not left to each adapter:
 - robots.txt is checked before the browser even opens, and again against
   the actual results URL before any extraction happens.
 - CAPTCHA / login-wall / explicit anti-bot detection short-circuits the
   run and is documented, never bypassed.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from config import RunConfig, SearchConfig
from models import FeasibilityReport, FareObservation
from robots_checker import RobotsGate
from utils.logger import get_logger
from utils.storage import save_json, save_text, timestamp_slug

if TYPE_CHECKING:
    from playwright.sync_api import Page


class BlockedByAccessControl(Exception):
    """Raised (and caught) when a CAPTCHA / login wall / explicit anti-bot
    challenge is detected. Signals 'stop and document', never 'work around'."""


class BaseAirfareAdapter(ABC):
    source_type: str = "direct_airline"   # override in subclass: direct_airline/ota/metasearch

    def __init__(self, run_config: RunConfig):
        self.cfg = run_config
        self.log = get_logger(self.cfg.source_name)
        self.cfg.ensure_dirs()
        self.robots = RobotsGate(self.cfg.base_url, self.cfg.user_agent)

    # ---- subclasses must implement these -------------------------------

    @property
    @abstractmethod
    def home_url(self) -> str:
        """Entry-point URL to load before interacting with the search form."""

    @abstractmethod
    def fill_search_form(self, page: "Page", search: SearchConfig) -> None:
        """Fill origin/destination/date/pax/cabin and submit the search."""

    @abstractmethod
    def wait_for_results(self, page: "Page") -> None:
        """Block until fare results are visibly rendered (or raise TimeoutError)."""

    @abstractmethod
    def extract_fares(self, page: "Page", search: SearchConfig) -> list[FareObservation]:
        """Parse the rendered page into structured FareObservation rows."""

    def detect_access_block(self, page: "Page") -> str | None:
        """Best-effort, non-invasive check for CAPTCHA/login/anti-bot walls.
        Return a short reason string if blocked, else None. Subclasses may
        override/extend; default checks a few common textual signals only —
        this NEVER attempts to solve/bypass anything it finds."""
        try:
            content = page.content().lower()
        except Exception:  # noqa: BLE001
            return None
        signals = [
            "captcha", "are you a robot", "unusual traffic",
            "access denied", "please verify you are a human",
            "bot detection", "cloudflare", "please enable javascript and cookies",
        ]
        for s in signals:
            if s in content:
                return f"Textual signal '{s}' found on page"
        return None

    # ---- orchestration (shared by every adapter) ------------------------

    def run(self, search: SearchConfig) -> FeasibilityReport:
        report = FeasibilityReport(
            source=self.cfg.source_name,
            source_type=self.source_type,
            test_route=f"{search.origin}-{search.destination}",
            trip_type=search.trip_type,
            run_started_at=__import__("datetime").datetime.now().isoformat(),
        )

        # 1. robots.txt for the homepage, checked BEFORE opening a browser.
        home_decision = self.robots.is_allowed(self.home_url)

        report.robots_txt_status = home_decision.status
        report.robots_txt_fetch_error = home_decision.fetch_error

        if home_decision.status != "allowed":
            if home_decision.status == "disallowed":
                report.notes.append(
                    "robots.txt explicitly disallows the target URL."
                )
                report.suitability = "NOT SUITABLE"
                report.suitability_reason = (
                    "robots.txt explicitly disallows the target URL; "
                    "browser automation was not attempted."
                )
            else:
                report.notes.append(
                    "robots.txt could not be verified; access was not attempted."
                )
                report.suitability = "NOT SUITABLE"
                report.suitability_reason = (
                    "robots.txt could not be verified; "
                    "browser automation was not attempted."
                )

            report.finish()
            self._persist_report(report)
            return report

        report.log("robots_check_home", "ok", f"{self.home_url} permitted")

        # 2. Run the browser flow, with repeat-query stability testing.
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            report.log("playwright_import", "error", "playwright not installed")
            report.suitability_reason = "Playwright is not installed in this environment."
            report.finish()
            self._persist_report(report)
            return report

        results_per_attempt = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=self.cfg.headless,
                slow_mo=self.cfg.slow_mo_ms,
                args=["--disable-http2"],          # ← fixes ERR_HTTP2_PROTOCOL_ERROR
            )
            context = browser.new_context(
                user_agent=self.cfg.user_agent,
                viewport={"width": 1366, "height": 768},
                locale="en-IN",
                timezone_id="Asia/Kolkata",
            )
            context.set_default_navigation_timeout(self.cfg.navigation_timeout_ms)
            context.set_default_timeout(self.cfg.action_timeout_ms)

            for attempt in range(1, self.cfg.repeat_queries + 1):
                page = context.new_page()
                try:
                    outcome = self._single_attempt(page, search, report, attempt)
                    results_per_attempt.append(outcome)
                except BlockedByAccessControl as exc:
                    report.log(f"attempt_{attempt}", "blocked", str(exc))
                    results_per_attempt.append("blocked")
                except Exception as exc:  # noqa: BLE001
                    report.log(f"attempt_{attempt}", "error", f"{type(exc).__name__}: {exc}")
                    results_per_attempt.append("error")
                finally:
                    page.close()
                if attempt < self.cfg.repeat_queries:
                    time.sleep(self.cfg.request_delay_seconds)

            browser.close()

        # 3. Stability verdict across repeat attempts.
        if results_per_attempt:
            if all(r == "ok" for r in results_per_attempt):
                report.repeat_query_result = "Stable"
            elif all(r == "blocked" for r in results_per_attempt):
                report.repeat_query_result = "Fails"
            else:
                report.repeat_query_result = "Variable"

        self._assign_suitability(report)
        report.finish()
        self._persist_report(report)
        return report

    # ---- internals --------------------------------------------------------

    def _single_attempt(self, page: "Page", search: SearchConfig,
                         report: FeasibilityReport, attempt: int) -> str:
        slug = f"{self.cfg.source_name}_{timestamp_slug()}_attempt{attempt}"

        page.goto(self.home_url, wait_until="domcontentloaded")
        report.log(f"nav_home_attempt{attempt}", "ok", self.home_url)

        block_reason = self.detect_access_block(page)
        if block_reason:
            self._save_screenshot(page, f"{slug}_home_blocked", report)
            raise BlockedByAccessControl(
                f"Access-control signal on homepage: {block_reason}. "
                f"Not attempting to bypass; stopping this attempt."
            )

        self.fill_search_form(page, search)
        report.log(f"fill_form_attempt{attempt}", "ok", "search form submitted")

        self.wait_for_results(page)

        # Re-check robots.txt against the ACTUAL results URL — search flows
        # often land on a different, more restricted path than the homepage.
        results_url = page.url
        results_decision = self.robots.is_allowed(results_url)
        if not results_decision.allowed:
            report.log(f"robots_check_results_attempt{attempt}", "blocked",
                       f"{results_url}: {results_decision.matched_rule_hint}")
            report.robots_txt_disallowed_paths.append(results_url)
            self._save_screenshot(page, f"{slug}_results_blocked_by_robots", report)
            raise BlockedByAccessControl(
                f"Results URL {results_url} is disallowed by robots.txt "
                f"({results_decision.matched_rule_hint}). Halting before extraction; "
                f"not scraping this path."
            )
        report.log(f"robots_check_results_attempt{attempt}", "ok", results_url)

        block_reason = self.detect_access_block(page)
        if block_reason:
            self._save_screenshot(page, f"{slug}_results_blocked", report)
            raise BlockedByAccessControl(
                f"Access-control signal on results page: {block_reason}. Stopping, not bypassing."
            )

        # Capture raw evidence BEFORE parsing, so debugging never depends on
        # extraction having succeeded.
        html_path = self.cfg.raw_html_dir / f"{slug}.html"
        save_text(page.content(), html_path)
        report.artifacts["raw_html"].append(str(html_path))

        self._save_screenshot(page, f"{slug}_results", report)

        observations = self.extract_fares(page, search)
        for obs in observations:
            report.observations.append(obs)

        json_path = self.cfg.json_dir / f"{slug}.json"
        save_json([o.__dict__ for o in observations], json_path)
        report.artifacts["json"].append(str(json_path))

        report.log(f"extract_attempt{attempt}", "ok" if observations else "error",
                   f"{len(observations)} fare rows parsed")

        if observations:
            self._update_fields_captured(report, observations)

        return "ok" if observations else "error"

    def _save_screenshot(self, page: "Page", slug: str, report: FeasibilityReport) -> None:
        path = self.cfg.screenshots_dir / f"{slug}.png"
        try:
            page.screenshot(path=str(path), full_page=True)
            report.artifacts["screenshots"].append(str(path))
        except Exception as exc:  # noqa: BLE001
            report.log("screenshot", "error", str(exc))

    def _update_fields_captured(self, report: FeasibilityReport, obs_list: list[FareObservation]) -> None:
        sample = obs_list[0]
        for field_name in ("airline", "flight_number", "departure_time", "arrival_time",
                           "fare_class_or_brand", "base_fare", "taxes", "fees",
                           "total_fare", "currency", "availability_state"):
            report.fields_captured[field_name] = getattr(sample, field_name) not in (None, "unknown")

    def _assign_suitability(self, report: FeasibilityReport) -> None:
        if report.robots_txt_status == "disallowed" or report.robots_txt_disallowed_paths:
            report.suitability = "NOT SUITABLE"
            report.suitability_reason = report.suitability_reason or (
                "robots.txt disallows the relevant path(s); this source cannot be "
                "automated within project policy."
            )
            return
        if any(s.status == "blocked" for s in report.steps):
            report.suitability = "NOT SUITABLE"
            report.suitability_reason = "An access-control signal (CAPTCHA/anti-bot/login) was observed."
            return
        if not report.observations:
            report.suitability = "LOW"
            report.suitability_reason = "Permitted by robots.txt, but no structured fares were extracted."
            return
        captured_ratio = sum(report.fields_captured.values()) / max(len(report.fields_captured), 1)
        if report.repeat_query_result == "Stable" and captured_ratio >= 0.8:
            report.suitability = "HIGH"
        elif captured_ratio >= 0.5:
            report.suitability = "MEDIUM"
        else:
            report.suitability = "LOW"
        report.suitability_reason = report.suitability_reason or (
            f"{captured_ratio:.0%} of key fields captured; repeat-query result: "
            f"{report.repeat_query_result}."
        )

    def _persist_report(self, report: FeasibilityReport) -> None:
        path = self.cfg.reports_dir / f"{self.cfg.source_name}_feasibility_report.json"
        save_json(_report_to_dict(report), path)
        self.log.info("Feasibility report written to %s (suitability=%s)",
                      path, report.suitability)


def _report_to_dict(report: FeasibilityReport) -> dict:
    d = dict(report.__dict__)
    d["observations"] = [o.__dict__ for o in report.observations]
    d["steps"] = [s.__dict__ for s in report.steps]
    return d
