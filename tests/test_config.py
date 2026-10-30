import pytest

from carwise.config import load_settings


def test_settings_file_is_valid() -> None:
    settings = load_settings()
    temperature = settings.llm.temperature
    assert temperature is None or temperature <= 0.2  # CLAUDE.md section 9
    effort = settings.llm.reasoning_effort
    assert effort in (None, "none", "minimal", "low")  # low effort when temperature is rejected
    assert settings.chunking.min_chars < settings.chunking.max_chars


def test_final_profile_uses_mini_only_for_generation() -> None:
    final = load_settings().profile("final")
    assert final.understand_model == "gpt-5.4-nano"
    assert final.generate_model == "gpt-5.4-mini"


def test_every_profile_model_has_a_price() -> None:
    settings = load_settings()
    for profile in settings.profiles.values():
        assert profile.understand_model in settings.prices
        assert profile.generate_model in settings.prices


def test_profile_comes_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARWISE_PROFILE", "final")
    assert load_settings().profile().generate_model == "gpt-5.4-mini"


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown profile"):
        load_settings().profile("prod")
