from carwise.ingest.probe import (
    ARTICLE_URLS,
    USER_AGENT,
    analyze,
    classify,
    parse_robots,
    slug,
)

ARTICLE_BODY = "<h2>מנוע</h2>" + "<p>" + "שלום עולם " * 80 + "</p>" * 1 + "<p>טקסט</p>" * 6


def test_slugs_are_unique_and_match_the_url_tail() -> None:
    slugs = [slug(url) for url in ARTICLE_URLS]
    assert len(set(slugs)) == len(ARTICLE_URLS) == 8
    assert slug("https://www.auto.co.il/articles/test-drives/road-tests/mg-s6/") == "mg-s6"


def test_robots_disallow_is_respected() -> None:
    parser = parse_robots("User-agent: *\nDisallow: /articles/\n")
    assert not parser.can_fetch(USER_AGENT, ARTICLE_URLS[0])
    assert parse_robots("").can_fetch(USER_AGENT, ARTICLE_URLS[0])


def test_classify_accepts_a_hebrew_article() -> None:
    assert classify(200, ARTICLE_BODY) == "ok"


def test_classify_detects_blocks_and_other_failures() -> None:
    assert classify(403, "") == "blocked"
    assert classify(200, "<title>Just a moment...</title>") == "blocked"
    assert classify(200, "<p>hello</p>") == "not_article"
    assert classify(500, "") == "error"


def test_analyze_counts_structure() -> None:
    result = analyze(ARTICLE_URLS[0], 200, ARTICLE_BODY, cached=False, detail="")
    assert result.verdict == "ok"
    assert result.headings == 1
    assert result.paragraphs >= 5
