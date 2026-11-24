# tes untuk paket ai/: rekomendasi, prediksi, cek sensor, data riwayat
import random
from datetime import datetime, timedelta, timezone

import pytest

from ai.anomaly import detect_anomaly, status_from_distance
from ai.predict import make_advisory, predict_occupancy
from ai.recommend import recommend_slot
from ai.seed_history import load_history

WIB = timezone(timedelta(hours=7))
NOW = datetime(2026, 11, 23, 8, 0, tzinfo=WIB)


def make_slots(floor, count=20, status="AVAILABLE", overrides=None):
    overrides = overrides or {}
    return [
        {"slotId": f"F{floor}-A{i:02d}", "floorNumber": floor,
         "status": overrides.get(i, status), "distance": None}
        for i in range(1, count + 1)
    ]


FLOORS_PEAK = [{"floorNumber": 1, "isOpen": True, "total": 20},
               {"floorNumber": 2, "isOpen": True, "total": 20}]
FLOORS_DEFAULT = [{"floorNumber": 1, "isOpen": True, "total": 20},
                  {"floorNumber": 2, "isOpen": False, "total": 20}]


# rekomendasi 
def test_peak_hour_recommends_floor_2():  # TC-01
    # lantai 1 terisi 18 dari 20, lantai 2 dibuka dan kosong
    slots = make_slots(1, overrides={i: "OCCUPIED" for i in range(1, 19)}) + make_slots(2)
    result = recommend_slot(slots, FLOORS_PEAK)
    assert result["floorNumber"] == 2
    assert result["slotId"].startswith("F2-")


def test_all_full_returns_none():  # TC-02
    slots = make_slots(1, status="OCCUPIED") + make_slots(2, status="OCCUPIED")
    assert recommend_slot(slots, FLOORS_PEAK) is None


def test_unknown_never_chosen():
    slots = make_slots(1, status="UNKNOWN", overrides={7: "AVAILABLE"})
    assert recommend_slot(slots, FLOORS_DEFAULT) == {"floorNumber": 1, "slotId": "F1-A07"}
    assert recommend_slot(make_slots(1, status="UNKNOWN"), FLOORS_DEFAULT) is None


def test_closed_floor_never_chosen():
    slots = make_slots(1, status="OCCUPIED") + make_slots(2)  # lantai 2 tertutup
    assert recommend_slot(slots, FLOORS_DEFAULT) is None


def test_empty_building_picks_first_slot_floor_1():
    result = recommend_slot(make_slots(1) + make_slots(2), FLOORS_DEFAULT)
    assert result == {"floorNumber": 1, "slotId": "F1-A01"}


def test_tie_break_is_deterministic():
    slots = make_slots(1) + make_slots(2)
    expected = recommend_slot(slots, FLOORS_PEAK)
    for seed in range(5):
        shuffled = slots[:]
        random.Random(seed).shuffle(shuffled)
        assert recommend_slot(shuffled, FLOORS_PEAK) == expected


def test_both_floors_overloaded_still_recommends():
    full = {i: "OCCUPIED" for i in range(1, 19)}
    slots = make_slots(1, overrides=full) + make_slots(2, overrides=full)
    assert recommend_slot(slots, FLOORS_PEAK) is not None


# cek sensor 
def test_out_of_range_500cm():  # TC-05
    assert detect_anomaly(500, NOW, NOW) == "OUT_OF_RANGE"
    assert detect_anomaly(1, NOW, NOW) == "OUT_OF_RANGE"


def test_stale_after_90_seconds():  # TC-05
    assert detect_anomaly(120, NOW - timedelta(seconds=90), NOW) == "STALE"
    assert detect_anomaly(None, None, NOW) == "STALE"


def test_ok_reading():
    assert detect_anomaly(120, NOW - timedelta(seconds=10), NOW) == "OK"
    assert detect_anomaly(120, NOW - timedelta(seconds=60), NOW) == "OK"  # tepat di batas


def test_reading_as_dict_from_backend():
    # bentuk laporan sensor yang dikirim backend (PUT /slots/{id}/status)
    ok = {"rawSensorValue": 18.4, "unit": "cm", "status": "OCCUPIED"}
    far = {"rawSensorValue": 500.0, "unit": "cm", "status": "OCCUPIED"}
    assert detect_anomaly(ok, NOW, NOW) == "OK"
    assert detect_anomaly(far, NOW, NOW) == "OUT_OF_RANGE"
    assert detect_anomaly(ok, NOW - timedelta(seconds=90), NOW) == "STALE"


def test_status_from_distance():
    assert status_from_distance(15) == "OCCUPIED"
    assert status_from_distance(29.9) == "OCCUPIED"
    assert status_from_distance(30) == "AVAILABLE"
    assert status_from_distance(150) == "AVAILABLE"
    assert status_from_distance(500) == "UNKNOWN"
    assert status_from_distance(1) == "UNKNOWN"


# data riwayat 
def test_history_shape():
    history = load_history()
    assert len(history) == 14 * 24 * 2
    assert {r["floorNumber"] for r in history} == {1, 2}
    assert {"date", "hour", "floorNumber", "occupancyPercent"} <= set(history[0])
    assert all(0 <= r["occupancyPercent"] <= 100 for r in history)


# prediksi 
def test_prediction_rush_hour():  # TC-06
    preds = predict_occupancy((6, 9), load_history())
    assert len(preds) == 4 * 2  # 4 jam x 2 lantai
    by_key = {(p["hour"], p["floorNumber"]): p["predictedOccupancyPercent"] for p in preds}
    assert by_key[(8, 1)] >= 85
    assert by_key[(6, 2)] < 20


@pytest.mark.parametrize("window", [(9, 6), (6, 6), (-1, 5), (6, 24), (6,)])
def test_invalid_window_raises(window):  # TC-06
    with pytest.raises(ValueError):
        predict_occupancy(window, load_history())


def test_advisory_suggests_opening_floor_2():
    preds = predict_occupancy((6, 9), load_history())
    text = make_advisory(preds, FLOORS_DEFAULT)
    assert "lantai 2" in text.lower()


def test_advisory_calm_when_low():
    preds = predict_occupancy((0, 3), load_history())
    assert "masih aman" in make_advisory(preds, FLOORS_DEFAULT)
