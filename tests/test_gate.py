"""Suggestions and templated refusals of the relevance gate (CW-201)."""

from datetime import date

from carwise.config import load_settings
from carwise.guardrails import (
    closest_by_score,
    corpus_overview,
    describe,
    hinted_cars,
    low_relevance_reply,
    mentioned,
    unknown_car_reply,
)
from carwise.registry import load_registry
from carwise.schemas import Chunk, RetrievedChunk

REGISTRY = load_registry()
GUARDRAILS = load_settings().guardrails


def hinted(text: str) -> list[str]:
    return hinted_cars(
        text,
        REGISTRY,
        GUARDRAILS.body_type_words,
        GUARDRAILS.powertrain_words,
        GUARDRAILS.max_suggestions,
    )


def hit(car_id: str, position: int, score: float) -> RetrievedChunk:
    car = REGISTRY.get(car_id)
    chunk = Chunk(
        chunk_id=f"{car_id}:{position:03d}",
        car=car_id,
        car_name=car.display_name,
        section="פרק",
        source_url=car.url,
        published=date(2026, 1, 1),
        text="טקסט",
        embed_text="טקסט",
    )
    return RetrievedChunk(chunk=chunk, score=score)


# --- hint words --------------------------------------------------------------------------
def test_electric_suv_hint_prefers_cars_matching_both() -> None:
    # Body type and powertrain both match beat one match: MG S6, EV9 (suv) and Aion (suv_coupe).
    assert hinted("יש לכם משהו כמו טסלה מודל Y, רכב פנאי חשמלי?") == [
        "kia_ev9",
        "mg_s6",
        "aion_ht",
    ]


def test_single_dimension_hint_and_hebrew_prefix() -> None:
    assert hinted("ומה עם הסדאן של BMW?") == ["audi_rs3"]  # prefix ה on סדאן
    assert hinted("מחפש היברידי נטען") == ["link_and_co_01"]  # "נטען" outscores mild hybrid


def test_no_hint_means_no_suggestion() -> None:
    assert hinted("מה דעתך על טויוטה קורולה?") == []


def test_hint_suggestions_respect_the_limit() -> None:
    assert len(hinted("רכב פנאי")) == GUARDRAILS.max_suggestions


def test_hint_words_never_contain_a_car_alias() -> None:
    words = [w for ws in GUARDRAILS.body_type_words.values() for w in ws] + [
        w for ws in GUARDRAILS.powertrain_words.values() for w in ws
    ]
    for car in REGISTRY.cars:
        assert mentioned(" ".join(words), car.aliases) == [], car.id


# --- chunk scores ------------------------------------------------------------------------
def test_closest_by_score_orders_cars_by_their_best_chunk() -> None:
    hits = [hit("mg_s6", 0, 0.70), hit("kia_ev9", 0, 0.80), hit("mg_s6", 1, 0.85)]
    assert closest_by_score(hits, 3) == ["mg_s6", "kia_ev9"]
    assert closest_by_score(hits, 1) == ["mg_s6"]
    assert closest_by_score([], 3) == []


# --- reply text --------------------------------------------------------------------------
def test_describe_uses_registry_facts_only() -> None:
    assert describe(REGISTRY.get("mg_s6")) == "MG S6 (רכב פנאי, חשמלי)"
    assert describe(REGISTRY.get("hyundai_elantra_n")) == "יונדאי אלנטרה N (בנזין)"


def test_overview_groups_all_eight_cars_by_powertrain() -> None:
    text = corpus_overview(REGISTRY)
    assert all(car.display_name in text for car in REGISTRY.cars)
    assert text.startswith("חשמלי: קיה EV9 (רכב פנאי), MG S6 (רכב פנאי)")
    assert "היברידי נטען: לינק אנד קו 01 (רכב פנאי)" in text


def test_unknown_car_reply_names_the_car_suggests_and_invites_follow_up() -> None:
    text = unknown_car_reply(["טסלה מודל Y"], REGISTRY, ["mg_s6", "kia_ev9"])
    assert text.startswith("אין לי מידע על טסלה מודל Y")
    assert "MG S6 (רכב פנאי, חשמלי)" in text and "קיה EV9" in text
    assert "ג'נסיס GV80" not in text  # only the suggestions, not the whole list
    assert "אפשר לשאול" in text


def test_reply_without_suggestions_lists_the_corpus() -> None:
    text = low_relevance_reply(REGISTRY, [])
    assert text.startswith("לא מצאתי בכתבות")
    assert all(car.display_name in text for car in REGISTRY.cars)
    assert "אפשר לשאול" in text
