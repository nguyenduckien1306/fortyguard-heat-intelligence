"""Tests for local validation of the documented heatmap request."""

import pytest
from pydantic import ValidationError

from tests.conftest import sample_heatmap_request
from frontend.utils.heatmap import build_heatmap_request_payload, parse_polygon_aoi


def test_heatmap_request_preserves_documented_geojson_shape() -> None:
    payload = sample_heatmap_request().model_dump(mode="json")

    assert set(payload) == {"polygon_aoi", "date_time", "granularity"}
    assert payload["polygon_aoi"]["type"] == "FeatureCollection"
    assert payload["polygon_aoi"]["features"][0]["geometry"]["type"] == "Polygon"
    assert payload["polygon_aoi"]["features"][0]["geometry"]["coordinates"][0][0] == [
        -74.017,
        40.705,
    ]
    assert payload["date_time"] == {
        "start_date": "2024-07-15",
        "start_time": "14:00",
        "filter_type": 1,
    }


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.pop("polygon_aoi"),
        lambda value: value["polygon_aoi"].pop("features"),
        lambda value: value["polygon_aoi"]["features"][0]["geometry"].update(
            {"type": "Point"}
        ),
        lambda value: value["polygon_aoi"]["features"][0]["geometry"].update(
            {"coordinates": [[[1.0, 2.0], [3.0, 4.0]]]}
        ),
        lambda value: value["date_time"].update({"start_date": "2024-02-30"}),
        lambda value: value["date_time"].update({"start_time": "25:00"}),
        lambda value: value.update({"granularity": "100"}),
    ],
)
def test_heatmap_request_rejects_obvious_structural_errors(change) -> None:
    payload = sample_heatmap_request().model_dump(mode="json")
    change(payload)

    with pytest.raises(ValidationError):
        from backend.models.heatmap import HeatmapRequest

        HeatmapRequest.model_validate(payload)


def test_parse_polygon_aoi_rejects_malformed_json() -> None:
    with pytest.raises(ValueError, match="valid JSON"):
        parse_polygon_aoi("not-json")


def test_build_payload_uses_date_and_time_controls() -> None:
    from datetime import date, time

    payload = build_heatmap_request_payload(
        sample_heatmap_request().model_dump(mode="json")["polygon_aoi"],
        date(2024, 7, 15),
        time(14, 0),
        100,
    )

    assert payload["date_time"]["start_date"] == "2024-07-15"
    assert payload["date_time"]["start_time"] == "14:00"
