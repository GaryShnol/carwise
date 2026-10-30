import io
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from carwise.config import FetchConfig
from carwise.ingest.fetch import (
    Fetcher,
    FetchStatus,
    HttpResponse,
    cache_path,
    classify,
    fallback_message,
    http_get,
    parse_robots,
    robots_url,
)
from carwise.registry import Car, load_registry

CONFIG = FetchConfig(user_agent="carwise-test/0", delay_s=3.0, timeout_s=1, retries=1)
# Synthetic page: enough Hebrew and paragraphs to pass the article check.
ARTICLE_BODY = "<h2>כותרת</h2><p>" + "מילה בדיקה " * 80 + "</p>" + "<p>טקסט</p>" * 6


def _cars() -> list[Car]:
    return load_registry().cars


class FakeSite:
    """Records every URL requested, so tests can prove the cache avoids the network."""

    def __init__(self, robots: HttpResponse, page: HttpResponse) -> None:
        self.robots = robots
        self.page = page
        self.requested: list[str] = []

    def __call__(self, url: str) -> HttpResponse:
        self.requested.append(url)
        return self.robots if url.endswith("/robots.txt") else self.page


def _site(page: HttpResponse | None = None, robots_text: str = "") -> FakeSite:
    return FakeSite(HttpResponse(200, robots_text), page or HttpResponse(200, ARTICLE_BODY))


def test_downloads_then_serves_from_cache_offline(tmp_path: Path) -> None:
    cars = _cars()[:2]
    sleeps: list[float] = []
    site = _site()
    results = Fetcher(CONFIG, tmp_path, get=site, sleep=sleeps.append).fetch_all(cars)
    assert [r.status for r in results] == [FetchStatus.DOWNLOADED] * 2
    assert cache_path(tmp_path, cars[0]).read_text(encoding="utf-8") == ARTICLE_BODY
    assert sleeps == [CONFIG.delay_s]  # polite delay between the two downloads only

    def offline(url: str) -> HttpResponse:
        raise AssertionError(f"network used for {url}")

    second = Fetcher(CONFIG, tmp_path, get=offline).fetch_all(cars)
    assert [r.status for r in second] == [FetchStatus.CACHED] * 2


def test_robots_disallow_is_respected(tmp_path: Path) -> None:
    site = _site(robots_text="User-agent: *\nDisallow: /articles/\n")
    result = Fetcher(CONFIG, tmp_path, get=site).fetch(_cars()[0])
    assert result.status is FetchStatus.DISALLOWED
    assert site.requested == [robots_url(_cars()[0].url)]
    assert not result.path.exists()


def test_crawl_delay_from_robots_wins_when_larger(tmp_path: Path) -> None:
    sleeps: list[float] = []
    site = _site(robots_text="User-agent: *\nCrawl-delay: 10\n")
    Fetcher(CONFIG, tmp_path, get=site, sleep=sleeps.append).fetch_all(_cars()[:2])
    assert sleeps == [10.0]


def test_blocked_page_is_not_cached_and_fallback_explains_manual_placement(
    tmp_path: Path,
) -> None:
    site = _site(page=HttpResponse(403, "Access denied"))
    results = Fetcher(CONFIG, tmp_path, get=site).fetch_all(_cars()[:1])
    assert results[0].status is FetchStatus.BLOCKED
    assert not results[0].path.exists()
    message = fallback_message(results, tmp_path)
    assert message is not None
    assert results[0].path.name in message
    assert "config/cars.yaml" in message


def test_fallback_is_none_when_everything_is_available(tmp_path: Path) -> None:
    results = Fetcher(CONFIG, tmp_path, get=_site()).fetch_all(_cars()[:1])
    assert fallback_message(results, tmp_path) is None


def test_unreadable_robots_stops_fetching(tmp_path: Path) -> None:
    site = FakeSite(HttpResponse(None, "", "timeout"), HttpResponse(200, ARTICLE_BODY))
    result = Fetcher(CONFIG, tmp_path, get=site).fetch(_cars()[0])
    assert result.status is FetchStatus.ERROR
    assert len(site.requested) == 1


def test_missing_robots_allows_everything() -> None:
    assert parse_robots("").can_fetch(CONFIG.user_agent, _cars()[0].url)


def test_classify_accepts_a_hebrew_article_even_with_a_captcha_script() -> None:
    assert classify(200, ARTICLE_BODY) is FetchStatus.DOWNLOADED
    body = ARTICLE_BODY + '<script src="https://www.google.com/recaptcha/api.js"></script>'
    assert classify(200, body) is FetchStatus.DOWNLOADED


def test_classify_detects_blocks_and_other_failures() -> None:
    assert classify(429, "") is FetchStatus.BLOCKED
    assert classify(200, "<title>Just a moment...</title>") is FetchStatus.BLOCKED
    assert classify(200, "<p>hello</p>") is FetchStatus.NOT_ARTICLE
    assert classify(500, "") is FetchStatus.ERROR


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x.test/", code, "err", Message(), io.BytesIO(b""))


class FakeOpener:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request, timeout: int) -> io.BytesIO:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return io.BytesIO(outcome.encode("utf-8"))


def test_http_get_retries_once_on_5xx_and_sends_user_agent() -> None:
    opener = FakeOpener([_http_error(503), "<p>ok</p>"])
    sleeps: list[float] = []
    response = http_get("https://x.test/", CONFIG, opener=opener, sleep=sleeps.append)
    assert response.status == 200
    assert response.body == "<p>ok</p>"
    assert sleeps == [CONFIG.delay_s]
    assert opener.requests[0].get_header("User-agent") == CONFIG.user_agent


def test_http_get_never_retries_a_4xx() -> None:
    opener = FakeOpener([_http_error(404)])
    response = http_get("https://x.test/", CONFIG, opener=opener, sleep=lambda _: None)
    assert response.status == 404
    assert len(opener.requests) == 1


def test_http_get_gives_up_after_one_retry() -> None:
    opener = FakeOpener([urllib.error.URLError("down"), urllib.error.URLError("down")])
    response = http_get("https://x.test/", CONFIG, opener=opener, sleep=lambda _: None)
    assert response.status is None
    assert "down" in response.detail


@pytest.mark.parametrize("car", _cars(), ids=lambda car: car.id)
def test_cache_file_is_named_after_the_slug(car: Car, tmp_path: Path) -> None:
    assert cache_path(tmp_path, car).name == f"{car.slug}.html"
