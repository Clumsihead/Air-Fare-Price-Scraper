from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests
from protego import Protego


@dataclass
class RobotsDecision:
    url: str
    user_agent: str
    status: str  # "allowed", "disallowed", or "unknown"
    robots_url: str
    matched_rule_hint: Optional[str] = None
    fetch_error: Optional[str] = None

    @property
    def allowed(self) -> bool:
        """Backward-compatible convenience property.

        Only an explicitly verified ALLOWED decision returns True.
        UNKNOWN and DISALLOWED both return False.
        """
        return self.status == "allowed"


class RobotsGate:
    def __init__(
        self,
        base_url: str,
        user_agent: str,
        timeout_seconds: int = 30,
        respect_robots_txt: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.respect_robots_txt = respect_robots_txt

        self.robots_url = f"{self.base_url}/robots.txt"

        self._parser: Optional[Protego] = None
        self._fetch_error: Optional[str] = None

        if self.respect_robots_txt:
            self._load()

    def _load(self) -> None:
        """Fetch and parse robots.txt.

        A fetch failure is represented as UNKNOWN.
        It must never be treated as ALLOWED.
        """
        try:
            response = requests.get(
                self.robots_url,
                timeout=self.timeout_seconds,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "text/plain,*/*",
                },
            )

            response.raise_for_status()

            self._parser = Protego.parse(response.text)

        except Exception as exc:
            self._fetch_error = f"{type(exc).__name__}: {exc}"
            self._parser = None

    def is_allowed(self, url: str) -> RobotsDecision:
        """Return a tri-state robots decision.

        allowed:
            robots.txt was successfully retrieved and permits the URL.

        disallowed:
            robots.txt was successfully retrieved and forbids the URL.

        unknown:
            robots.txt could not be verified.
        """
        if not self.respect_robots_txt:
            return RobotsDecision(
                url=url,
                user_agent=self.user_agent,
                status="allowed",
                robots_url=self.robots_url,
                matched_rule_hint="robots.txt checks disabled by configuration",
            )

        if self._parser is None:
            return RobotsDecision(
                url=url,
                user_agent=self.user_agent,
                status="unknown",
                robots_url=self.robots_url,
                fetch_error=self._fetch_error,
            )

        try:
            allowed = self._parser.can_fetch(url, self.user_agent)

            if allowed:
                return RobotsDecision(
                    url=url,
                    user_agent=self.user_agent,
                    status="allowed",
                    robots_url=self.robots_url,
                )

            return RobotsDecision(
                url=url,
                user_agent=self.user_agent,
                status="disallowed",
                robots_url=self.robots_url,
                matched_rule_hint="robots.txt disallows this URL",
            )

        except Exception as exc:
            return RobotsDecision(
                url=url,
                user_agent=self.user_agent,
                status="unknown",
                robots_url=self.robots_url,
                fetch_error=f"{type(exc).__name__}: {exc}",
            )