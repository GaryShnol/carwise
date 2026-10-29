"""Download the eight articles once and serve them from data/raw/ afterwards.

Why a cache and not a fetch per run: the articles belong to the publisher, so we
hit the site as little as possible, and every later step (cleaning, chunking,
the retrieval eval) must work offline. Why so careful: identifiable User-Agent,
robots.txt, a delay and one retry are what a polite scraper does, and a block is
reported to the user instead of worked around (the CW-002 spike findings).
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import IO, Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from carwise.config import FetchConfig
from carwise.registry import Car

MIN_HEBREW_CHARS = 500
MIN_PARAGRAPHS = 5
BLOCK_MARKERS = ("just a moment", "cf-chl", "captcha", "access denied", "attention required")

FALLBACK_MESSAGE = """\
Some articles could not be downloaded automatically.
Save each missing article page from your browser as an HTML file in {raw_dir}/,
named after the last part of its URL (for example {raw_dir}/mg-s6.html), then run
`python -m app ingest` again. Missing: {missing}.
The URL of every article is in config/cars.yaml."""

_HEBREW = re.compile(r"[\u0590-\u05ff]")
_PARAGRAPH = re.compile(r"<p[\s>]", re.IGNORECASE)

Opener = Callable[..., IO[bytes]]
Sleep = Callable[[float], None]


class FetchStatus(StrEnum):
    CACHED = "cached"
    DOWNLOADED = "downloaded"
    BLOCKED = "blocked"
    NOT_ARTICLE = "not_article"
    ERROR = "error"
    DISALLOWED = "disallowed_by_robots"


@dataclass(frozen=True)
class FetchResult:
    car_id: str
    path: Path
    status: FetchStatus
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status in (FetchStatus.CACHED, FetchStatus.DOWNLOADED)


@dataclass(frozen=True)
class HttpResponse:
    status: int | None
    body: str
    detail: str = ""


def cache_path(raw_dir: Path, car: Car) -> Path:
    return raw_dir / f"{car.slug}.html"


def looks_like_article(body: str) -> bool:
    """Enough Hebrew text and paragraphs to be an article body rather than a stub page."""
    return (
        len(_HEBREW.findall(body)) >= MIN_HEBREW_CHARS
        and len(_PARAGRAPH.findall(body)) >= MIN_PARAGRAPHS
    )


def classify(status: int | None, body: str) -> FetchStatus:
    """Decide whether a response is a usable article, a block, or something else.

    Order matters: real article pages embed captcha scripts (comment forms), so
    block markers are only trusted on pages that do not contain an article body.
    """
    if status in (401, 403, 429):
        return FetchStatus.BLOCKED
    if status == 200 and looks_like_article(body):
        return FetchStatus.DOWNLOADED
    if any(marker in body.lower() for marker in BLOCK_MARKERS):
        return FetchStatus.BLOCKED
    return FetchStatus.NOT_ARTICLE if status == 200 else FetchStatus.ERROR


def http_get(
    url: str,
    config: FetchConfig,
    *,
    opener: Opener = urllib.request.urlopen,
    sleep: Sleep = time.sleep,
) -> HttpResponse:
    """One GET with a single retry on network errors and 5xx; a 4xx is final."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": config.user_agent,
            "Accept": "text/html",
            "Accept-Language": "he,en;q=0.5",
        },
    )
    detail = ""
    for attempt in range(config.retries + 1):
        try:
            with opener(request, timeout=config.timeout_s) as response:
                status: Any = getattr(response, "status", 200)
                return HttpResponse(int(status), response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as error:
            body = error.read(20000).decode("utf-8", errors="replace")
            if error.code < 500:
                return HttpResponse(error.code, body, str(error))
            detail = str(error)
        except (urllib.error.URLError, TimeoutError) as error:
            detail = str(error)
        if attempt < config.retries:
            sleep(config.delay_s)
    return HttpResponse(None, "", detail)


def parse_robots(text: str) -> RobotFileParser:
    parser = RobotFileParser()
    parser.parse(text.splitlines())
    return parser


def robots_url(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}/robots.txt"


def load_robots(response: HttpResponse) -> RobotFileParser | None:
    """A missing robots.txt (404) allows everything; any other failure means do not fetch."""
    if response.status == 200:
        return parse_robots(response.body)
    if response.status == 404:
        return parse_robots("")
    return None


class Fetcher:
    """Fetches the registry's articles into the cache, reading robots.txt only if needed."""

    def __init__(
        self,
        config: FetchConfig,
        raw_dir: Path,
        *,
        get: Callable[[str], HttpResponse] | None = None,
        sleep: Sleep = time.sleep,
    ) -> None:
        self.config = config
        self.raw_dir = raw_dir
        self._get = get or (lambda url: http_get(url, config, sleep=sleep))
        self._sleep = sleep
        self._robots: dict[str, RobotFileParser | None] = {}
        self._fetched_any = False

    def _robots_for(self, url: str) -> RobotFileParser | None:
        key = robots_url(url)
        if key not in self._robots:
            self._robots[key] = load_robots(self._get(key))
        return self._robots[key]

    def _delay(self, robots: RobotFileParser) -> float:
        crawl_delay = robots.crawl_delay(self.config.user_agent)
        return max(self.config.delay_s, float(crawl_delay or 0))

    def fetch(self, car: Car, *, force: bool = False) -> FetchResult:
        path = cache_path(self.raw_dir, car)
        if path.exists() and not force:
            return FetchResult(car.id, path, FetchStatus.CACHED)
        robots = self._robots_for(car.url)
        if robots is None:
            return FetchResult(car.id, path, FetchStatus.ERROR, "robots.txt unavailable")
        if not robots.can_fetch(self.config.user_agent, car.url):
            return FetchResult(car.id, path, FetchStatus.DISALLOWED)
        if self._fetched_any:
            self._sleep(self._delay(robots))
        self._fetched_any = True
        response = self._get(car.url)
        status = classify(response.status, response.body)
        if status is FetchStatus.DOWNLOADED:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(response.body, encoding="utf-8", newline="")
        return FetchResult(car.id, path, status, response.detail)

    def fetch_all(self, cars: list[Car], *, force: bool = False) -> list[FetchResult]:
        return [self.fetch(car, force=force) for car in cars]


def fallback_message(results: list[FetchResult], raw_dir: Path) -> str | None:
    """Manual-placement instructions, or None when every article is available."""
    missing = [result.path.name for result in results if not result.ok]
    if not missing:
        return None
    return FALLBACK_MESSAGE.format(raw_dir=raw_dir.as_posix(), missing=", ".join(missing))
