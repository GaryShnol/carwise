from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from carwise.registry import Registry, load_registry, normalize_alias, url_slug


def _car(car_id: str, **overrides: Any) -> dict[str, Any]:
    car: dict[str, Any] = {
        "id": car_id,
        "display_name": f"רכב {car_id}",
        "aliases_he": [],
        "aliases_latin": [car_id.upper()],
        "body_type": "suv",
        "body_type_quote": "רכב פנאי",
        "powertrain": None,
        "powertrain_quote": None,
        "url": f"https://example.test/articles/{car_id}/",
        "slug": car_id,
    }
    car.update(overrides)
    return car


def test_registry_lists_the_eight_cars() -> None:
    registry = load_registry()
    assert len(registry.cars) == 8
    assert all(car.url.startswith("https://www.auto.co.il/") for car in registry.cars)


def test_ids_slugs_and_aliases_are_unique() -> None:
    registry = load_registry()
    ids = [car.id for car in registry.cars]
    slugs = [car.slug for car in registry.cars]
    aliases = [normalize_alias(alias) for car in registry.cars for alias in set(car.aliases)]
    assert len(set(ids)) == len(ids)
    assert len(set(slugs)) == len(slugs)
    assert len(set(aliases)) == len(aliases)


def test_every_car_has_a_hebrew_or_latin_alias() -> None:
    for car in load_registry().cars:
        assert car.aliases_he or car.aliases_latin, car.id


def test_get_by_id() -> None:
    registry = load_registry()
    assert registry.get("mg_s6").slug == "mg-s6"
    with pytest.raises(KeyError):
        registry.get("toyota_corolla")


def test_duplicate_alias_across_cars_is_rejected() -> None:
    with pytest.raises(ValidationError, match="alias"):
        Registry.model_validate(
            {"cars": [_car("a1", aliases_latin=["X1"]), _car("b2", aliases_latin=["x1"])]}
        )


def test_duplicate_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate car id"):
        Registry.model_validate({"cars": [_car("a1"), _car("a1", aliases_latin=["Z"])]})


def test_slug_must_match_url() -> None:
    with pytest.raises(ValidationError, match="slug"):
        Registry.model_validate({"cars": [_car("a1", slug="other")]})


def test_value_without_quote_is_rejected() -> None:
    with pytest.raises(ValidationError, match="powertrain"):
        Registry.model_validate({"cars": [_car("a1", powertrain="electric")]})


def test_unknown_body_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Registry.model_validate({"cars": [_car("a1", body_type="minivan")]})


def test_load_from_custom_path(tmp_path: Path) -> None:
    path = tmp_path / "cars.yaml"
    path.write_text(yaml.safe_dump({"cars": [_car("a1")]}, allow_unicode=True), encoding="utf-8")
    assert load_registry(path).cars[0].id == "a1"


def test_url_slug() -> None:
    assert url_slug("https://www.auto.co.il/articles/test-drives/road-tests/mg-s6/") == "mg-s6"
