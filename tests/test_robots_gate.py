from pathlib import Path
from unittest.mock import Mock, patch

from robots_checker import RobotsGate


FIXTURE = Path(__file__).parent / "fixture_indigo_robots_trimmed.txt"


def _mock_response(text: str) -> Mock:
    response = Mock()
    response.text = text
    response.raise_for_status.return_value = None
    return response


def test_allowed_url():
    robots_text = FIXTURE.read_text(encoding="utf-8")

    with patch(
        "robots_checker.requests.get",
        return_value=_mock_response(robots_text),
    ):
        gate = RobotsGate(
            base_url="https://www.goindigo.in",
            user_agent="AirfareScraper/0.1",
        )

        decision = gate.is_allowed(
            "https://www.goindigo.in/about-us.html"
        )

    assert decision.status == "allowed"
    assert decision.allowed is True
    assert decision.fetch_error is None


def test_disallowed_search_url():
    robots_text = FIXTURE.read_text(encoding="utf-8")

    with patch(
        "robots_checker.requests.get",
        return_value=_mock_response(robots_text),
    ):
        gate = RobotsGate(
            base_url="https://www.goindigo.in",
            user_agent="AirfareScraper/0.1",
        )

        decision = gate.is_allowed(
            "https://www.goindigo.in/search.html"
        )

    assert decision.status == "disallowed"
    assert decision.allowed is False


def test_disallowed_booking_url():
    robots_text = FIXTURE.read_text(encoding="utf-8")

    with patch(
        "robots_checker.requests.get",
        return_value=_mock_response(robots_text),
    ):
        gate = RobotsGate(
            base_url="https://www.goindigo.in",
            user_agent="AirfareScraper/0.1",
        )

        decision = gate.is_allowed(
            "https://www.goindigo.in/book/test"
        )

    assert decision.status == "disallowed"
    assert decision.allowed is False


def test_robots_fetch_timeout_returns_unknown():
    with patch(
        "robots_checker.requests.get",
        side_effect=TimeoutError("robots.txt request timed out"),
    ):
        gate = RobotsGate(
            base_url="https://www.goindigo.in",
            user_agent="AirfareScraper/0.1",
        )

        decision = gate.is_allowed(
            "https://www.goindigo.in/about-us.html"
        )

    assert decision.status == "unknown"
    assert decision.allowed is False
    assert decision.fetch_error is not None
    assert "TimeoutError" in decision.fetch_error


def test_robots_http_error_returns_unknown():
    response = Mock()
    response.raise_for_status.side_effect = RuntimeError(
        "HTTP 503 Service Unavailable"
    )

    with patch(
        "robots_checker.requests.get",
        return_value=response,
    ):
        gate = RobotsGate(
            base_url="https://www.goindigo.in",
            user_agent="AirfareScraper/0.1",
        )

        decision = gate.is_allowed(
            "https://www.goindigo.in/about-us.html"
        )

    assert decision.status == "unknown"
    assert decision.allowed is False
    assert decision.fetch_error is not None