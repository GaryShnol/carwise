"""CW-002 spike: can the eight articles be fetched politely and automatically?

Why a spike before the real downloader: if the site blocks scripted access, the
whole ingestion design changes (manual files in data/raw/), and we want to know
that before building on it. The probe fetches each URL once, honours robots.txt,
identifies itself, and never works around a block. Pages that load are cached in
data/raw/ (not committed), so the real downloader (CW-101) does not hit the site again.

Run from the repository root:  uv run python -m carwise.ingest.probe
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from carwise.config import load_settings

USER_AGENT = "carwise-takehome/0.1 (+https://github.com/GaryShnol/carwise)"
ROBOTS_URL = "https://www.auto.co.il/robots.txt"
ARTICLE_URLS = [
    "https://www.auto.co.il/articles/test-drives/road-tests/citroen-c3-2026/",
    "https://www.auto.co.il/articles/test-drives/road-tests/audi-rs3-fl/",
    "https://www.auto.co.il/articles/test-drives/road-tests/long-term-report-kia-ev9-4/",
    "https://www.auto.co.il/articles/test-drives/road-tests/mg-s6/",
    "https://www.auto.co.il/articles/test-drives/road-tests/hyundai-elantra-n-manual/",
    "https://www.auto.co.il/articles/test-drives/road-tests/aion-ht/",
    "https://www.auto.co.il/articles/test-drives/road-tests/link-and-co-01-2026/",
    "https://www.auto.co.il/articles/test-drives/road-tests/genesis-gv80-2026/",
]
MIN_DELAY_S = 3.0
TIMEOUT_S = 20
MIN_HEBREW_CHARS = 500
MIN_PARAGRAPHS = 5
BLOCK_MARKERS = ("just a moment", "cf-chl", "captcha", "access denied", "attention required")

FALLBACK_MESSAGE = """\
The articles could not be downloaded automatically.
Please save each article page as an HTML file in data/raw/, named after the last part
of its URL (for example data/raw/mg-s6.html), then run the ingest command again.
The URL list is in config/cars.yaml."""

_HEBREW = re.compile(r"[֐-׿]")
_HEADING = re.compile(r"<h[1-4][\s>]", re.IGNORECASE)
_PARAGRAPH = re.compile(r"<p[\s>]", re.IGNORECASE)


@dataclass
class ProbeResult:
    url: str
    robots_allowed: bool
    status: int | None
    verdict: str  # ok | blocked | not_article | error | skipped_by_robots
    size_bytes: int
    hebrew_chars: int
    headings: int
    paragraphs: int
    from_cache: bool
    detail: str


def slug(url: str) -> str:
    """Cache file stem: the last path segment, which is unique among the eight URLs."""
    return urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]


def parse_robots(text: str) -> RobotFileParser:
    parser = RobotFileParser()
    parser.parse(text.splitlines())
    return parser


def looks_like_article(body: str) -> bool:
    """Enough Hebrew text and paragraphs to be an article body rather than a stub page."""
    return (
        len(_HEBREW.findall(body)) >= MIN_HEBREW_CHARS
        and len(_PARAGRAPH.findall(body)) >= MIN_PARAGRAPHS
    )


def classify(status: int | None, body: str) -> str:
    """Decide whether a response is a usable article, a block, or something else.

    Order matters: real article pages legitimately embed captcha scripts (comment forms),
    so block markers are only trusted on pages that do not contain an article body.
    """
    if status in (401, 403, 429):
        return "blocked"
    if status == 200 and looks_like_article(body):
        return "ok"
    lowered = body.lower()
    if any(marker in lowered for marker in BLOCK_MARKERS):
        return "blocked"
    return "not_article" if status == 200 else "error"


def http_get(url: str, retries: int = 1) -> tuple[int | None, str, str]:
    """One polite GET with a single retry on network errors and 5xx; never retries a 4xx."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html",
            "Accept-Language": "he,en;q=0.5",
        },
    )
    detail = ""
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310
                return response.status, response.read().decode("utf-8", errors="replace"), ""
        except urllib.error.HTTPError as error:
            body = error.read(20000).decode("utf-8", errors="replace")
            if error.code < 500:
                return error.code, body, str(error)
            detail = str(error)
        except (urllib.error.URLError, TimeoutError) as error:
            detail = str(error)
        if attempt < retries:
            time.sleep(MIN_DELAY_S)
    return None, "", detail


def load_robots() -> tuple[RobotFileParser | None, str]:
    """Fetch robots.txt. A missing file (404) allows everything; any other failure stops us."""
    status, body, detail = http_get(ROBOTS_URL)
    if status == 200:
        return parse_robots(body), "robots.txt read"
    if status == 404:
        return parse_robots(""), "no robots.txt (404): nothing disallowed"
    return None, f"robots.txt unavailable (status {status}, {detail}): not fetching"


def analyze(url: str, status: int | None, body: str, *, cached: bool, detail: str) -> ProbeResult:
    return ProbeResult(
        url=url,
        robots_allowed=True,
        status=status,
        verdict=classify(status, body),
        size_bytes=len(body.encode("utf-8")),
        hebrew_chars=len(_HEBREW.findall(body)),
        headings=len(_HEADING.findall(body)),
        paragraphs=len(_PARAGRAPH.findall(body)),
        from_cache=cached,
        detail=detail,
    )


def probe(raw_dir: Path, force: bool) -> tuple[list[ProbeResult], str]:
    robots, robots_note = load_robots()
    delay = MIN_DELAY_S
    if robots is not None:
        delay = max(delay, float(robots.crawl_delay(USER_AGENT) or 0))
    results: list[ProbeResult] = []
    raw_dir.mkdir(parents=True, exist_ok=True)
    fetched_any = False
    for url in ARTICLE_URLS:
        cache_file = raw_dir / f"{slug(url)}.html"
        if cache_file.exists() and not force:
            body = cache_file.read_text(encoding="utf-8")
            results.append(analyze(url, 200, body, cached=True, detail="cache"))
            continue
        if robots is None or not robots.can_fetch(USER_AGENT, url):
            results.append(
                ProbeResult(url, False, None, "skipped_by_robots", 0, 0, 0, 0, False, robots_note)
            )
            continue
        if fetched_any:
            time.sleep(delay)
        fetched_any = True
        status, body, detail = http_get(url)
        result = analyze(url, status, body, cached=False, detail=detail)
        if result.verdict == "ok":
            cache_file.write_text(body, encoding="utf-8")
        results.append(result)
    return results, robots_note


def print_report(results: list[ProbeResult], robots_note: str) -> bool:
    print(f"robots: {robots_note}")
    print(f"{'article':34} {'status':>6} {'verdict':18} {'KB':>5} {'heb':>6} {'h':>3} {'p':>4}")
    for r in results:
        name = slug(r.url) + (" (cache)" if r.from_cache else "")
        print(
            f"{name:34} {str(r.status):>6} {r.verdict:18} {r.size_bytes // 1024:>5} "
            f"{r.hebrew_chars:>6} {r.headings:>3} {r.paragraphs:>4}"
        )
    all_ok = all(r.verdict == "ok" for r in results)
    print("\nDECISION: automatic download works." if all_ok else f"\n{FALLBACK_MESSAGE}")
    return all_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CW-002: probe access to the eight articles")
    parser.add_argument("--force", action="store_true", help="ignore the cache and fetch again")
    args = parser.parse_args(argv)
    paths = load_settings().paths
    results, robots_note = probe(Path(paths.raw_dir), args.force)
    log_dir = Path(paths.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    report = {"robots": robots_note, "results": [asdict(r) for r in results]}
    (log_dir / "probe_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if print_report(results, robots_note) else 1


if __name__ == "__main__":
    sys.exit(main())
