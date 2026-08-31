"""
robots.txt gate.

Per the Validation Register (Section 6): "Check robots.txt and terms of
service before automation" and "Do not bypass CAPTCHAs, authentication,
anti-bot controls, paywalls or other access restrictions."

This module is deliberately the FIRST thing every adapter calls, and it is
checked again for the *actual* URL the browser lands on (not just the
starting URL), because search/booking flows often redirect into paths with
different robots rules than the homepage.

IMPORTANT implementation note: Python's stdlib `urllib.robotparser` does
NOT correctly implement the widely-used `*` wildcard / `$` end-anchor
extensions to robots.txt (e.g. `Disallow: /book/*`). Verified directly
against IndiGo's real robots.txt during development: stdlib robotparser
reported `/book/flight-select.html` as ALLOWED even though
`Disallow: /book/*` is present, because it only does literal prefix
matching. That is a serious false-negative for a compliance tool, so this
module uses `protego` (the parser Scrapy uses), which implements the
Google/de-facto extended spec including wildcards.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from protego import Protego


@dataclass
class RobotsDecision:
    url: str
    user_agent: str
    allowed: bool
    robots_url: str
    matched_rule_hint: str | None = None
    fetch_error: str | None = None


class RobotsGate:
    """Wrapper around protego, with a requests-based fetch so we control
    timeout/UA and can persist the raw robots.txt for the audit trail.

    Fetch-failure policy (distinguishes two very different situations):
      - Network error / timeout: robots.txt is unreachable, NOT the same
        as "disallowed". We log a warning and allow the run to proceed so
        the browser can produce real evidence — but we record the fetch
        failure prominently in the report so it isn't silently ignored.
      - Explicit Disallow rule matched: hard block, run halts immediately.
    """

    def __init__(self, base_url: str, user_agent: str, timeout: int = 30):
        self.base_url = base_url
        self.user_agent = user_agent
        self.timeout = timeout
        self.robots_url = urljoin(base_url, "/robots.txt")
        self._parser: Protego | None = None
        self._raw_text: str | None = None
        self._fetch_error: str | None = None
        self._fetch_unreachable: bool = False   # True = network/timeout, not a Disallow
        self._load()

    def _load(self) -> None:
        try:
            resp = requests.get(
                self.robots_url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            self._raw_text = resp.text
            self._parser = Protego.parse(self._raw_text)
        except Exception as exc:  # noqa: BLE001 - record any failure for the report
            self._fetch_error = str(exc)
            self._fetch_unreachable = True
            self._parser = None

    @property
    def raw_text(self) -> str | None:
        return self._raw_text

    def is_allowed(self, url: str) -> RobotsDecision:
        if self._fetch_unreachable or self._parser is None:
            # Network error / timeout: we cannot confirm either way.
            # Log it clearly, but allow the run to proceed so the browser
            # can produce real evidence. The fetch_error field in the report
            # will make this explicit — it is NOT treated as a silent pass.
            return RobotsDecision(
                url=url,
                user_agent=self.user_agent,
                allowed=True,   # proceed, but with fetch_error set as a warning
                robots_url=self.robots_url,
                fetch_error=self._fetch_error,
                matched_rule_hint=(
                    "WARNING: robots.txt could not be fetched (network error / timeout). "
                    "Proceeding with browser run so real evidence can be collected, but "
                    "this is NOT a confirmed 'allowed' — review robots.txt manually before "
                    "any repeated/production use of this source."
                ),
            )

        allowed = self._parser.can_fetch(url, self.user_agent)
        hint = None
        if not allowed:
            hint = "URL matches a Disallow rule (wildcard-aware match via protego)."
        return RobotsDecision(
            url=url,
            user_agent=self.user_agent,
            allowed=allowed,
            robots_url=self.robots_url,
            matched_rule_hint=hint,
        )
