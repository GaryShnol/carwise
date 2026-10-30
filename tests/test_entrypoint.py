import shutil
from pathlib import Path

import pytest
import yaml

from app.__main__ import PENDING, main
from carwise.config import DEFAULT_CONFIG_PATH
from carwise.registry import load_registry

FIXTURE = Path(__file__).parent / "fixtures" / "article.html"


def test_pending_commands_report_their_ticket(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["eval"]) == 2
    assert PENDING["eval"] in capsys.readouterr().out


def test_unknown_command_is_rejected() -> None:
    with pytest.raises(SystemExit):
        main(["bogus"])


def _settings_with_raw_dir(tmp_path: Path, raw_dir: Path) -> Path:
    settings = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    settings["paths"]["raw_dir"] = raw_dir.as_posix()
    settings["paths"]["index_dir"] = (tmp_path / "index").as_posix()
    settings["embeddings"]["provider"] = "fake"  # no model download in unit tests
    path = tmp_path / "settings.yaml"
    path.write_text(yaml.safe_dump(settings, allow_unicode=True), encoding="utf-8")
    return path


def _cache_fixture_for_every_car(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    for car in load_registry().cars:  # every article "cached", so nothing touches the network
        shutil.copy(FIXTURE, raw_dir / f"{car.slug}.html")
    monkeypatch.setenv("CARWISE_CONFIG", str(_settings_with_raw_dir(tmp_path, raw_dir)))


def test_ingest_reports_counts_from_the_cache_without_body_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cars = load_registry().cars
    _cache_fixture_for_every_car(tmp_path, monkeypatch)

    assert main(["ingest"]) == 0
    out = capsys.readouterr().out
    assert f"fetch: {len(cars)} cached" in out
    assert all(f"[{car.id}]" in out for car in cars)
    assert "first headings: הרכב הנבחן / מה המנוע? / יתרונות" in out
    assert "פסקת פתיחה" not in out  # paragraph text never reaches the report
    assert "יתרון ראשון" not in out
    assert f"cleaned {len(cars)} of {len(cars)} articles" in out
    assert "chunks per car (length in chars: min / median / max)" in out
    assert all(f"  {car.id} " in out for car in cars)
    assert "  total " in out
    assert "index built: " in out

    assert main(["ingest"]) == 0
    assert "index up to date" in capsys.readouterr().out


def test_search_prints_metadata_without_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _cache_fixture_for_every_car(tmp_path, monkeypatch)
    assert main(["ingest"]) == 0
    capsys.readouterr()

    assert main(["search", "מה המנוע?", "--car", "mg_s6", "--top-k", "2"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].split() == ["rank", "score", "chunk_id", "car", "section"]
    assert 1 <= len(lines) - 1 <= 2  # the fixture article is a single chunk
    assert all(" mg_s6:" in line and " mg_s6 " in line for line in lines[1:])
    assert not any("פסקת פתיחה" in line for line in lines)  # chunk text is never printed


def test_search_without_index_explains_what_to_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CARWISE_CONFIG", str(_settings_with_raw_dir(tmp_path, tmp_path / "raw")))
    assert main(["search", "שאלה"]) == 1
    assert "python -m app ingest" in capsys.readouterr().out


def test_ingest_prints_manual_placement_message_when_articles_are_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from carwise.ingest import fetch

    monkeypatch.setenv("CARWISE_CONFIG", str(_settings_with_raw_dir(tmp_path, tmp_path / "raw")))
    monkeypatch.setattr(fetch, "http_get", lambda url, config, **_: fetch.HttpResponse(None, ""))

    assert main(["ingest"]) == 1
    out = capsys.readouterr().out
    assert "could not be downloaded automatically" in out
    assert "cleaned 0 of 8 articles" in out
    assert "index not built" in out
