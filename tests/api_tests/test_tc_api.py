"""Uji endpoint untuk TC-01 s.d. TC-09."""
from conftest import BASE, DASH, DEVICE, floor, slot, status_body, tap_body


def scenario(client, name):
    assert client.post(f"{BASE}/dev/scenario/{name}", headers=DEVICE).status_code == 200


def test_tc01_tap_valid_peak_hour_recommends_floor_2(client):
    scenario(client, "peak_hour")
    r = client.post(f"{BASE}/gate/entry-tap", headers=DEVICE, json=tap_body())
    assert r.status_code == 200
    body = r.json()
    assert body["gateAction"] == "OPEN_BARRIER"
    assert body["recommendation"]["floorNumber"] == 2
    slot_id = body["recommendation"]["slotId"]
    assert body["displayMessage"] == f"Lantai 2 - Slot {slot_id}"
    assert slot(client, slot_id)["ledColor"] == "YELLOW"


def test_tc02_all_full_returns_null_but_opens_barrier(client):
    scenario(client, "all_full")
    r = client.post(f"{BASE}/gate/entry-tap", headers=DEVICE, json=tap_body())
    assert r.status_code == 200
    assert r.json()["recommendation"] is None
    assert r.json()["gateAction"] == "OPEN_BARRIER"
    assert "penuh" in r.json()["displayMessage"].lower()


def test_tc03_invalid_card(client):
    r = client.post(f"{BASE}/gate/entry-tap", headers=DEVICE, json=tap_body("RFID-TIDAK-ADA"))
    assert r.status_code == 400
    assert r.json() == {
        "status": 400,
        "code": "INVALID_CARD",
        "message": "Kartu tidak terdaftar; palang tidak dibuka",
    }


def test_tc04_park_and_exit_led_and_counts(client):
    before = floor(client, 2)["available"]
    r = client.put(f"{BASE}/slots/F2-A17/status", headers=DEVICE, json=status_body("OCCUPIED"))
    assert r.status_code == 200
    assert r.json() == {"slotId": "F2-A17", "currentStatus": "OCCUPIED", "ledCommand": {"color": "RED", "sent": True}}
    assert floor(client, 2)["available"] == before - 1
    r = client.put(f"{BASE}/slots/F2-A17/status", headers=DEVICE, json=status_body("AVAILABLE", 150))
    assert r.json()["ledCommand"]["color"] == "GREEN"
    assert floor(client, 2)["available"] == before


def test_tc05_out_of_range_sensor_becomes_unknown(client):
    r = client.put(f"{BASE}/slots/F1-A03/status", headers=DEVICE, json=status_body("OCCUPIED", 500))
    assert r.json()["currentStatus"] == "UNKNOWN"
    assert r.json()["ledCommand"]["color"] == "OFF"
    f1 = floor(client, 1)
    assert f1["unknown"] == 1 and f1["available"] == 19  # UNKNOWN dihitung terpisah


def test_tc05_stale_sensor_becomes_unknown_and_not_recommended(client):
    scenario(client, "sensor_stale")
    f1 = floor(client, 1)
    assert f1["unknown"] == 2
    assert slot(client, "F1-A05")["status"] == "UNKNOWN"
    assert slot(client, "F1-A05")["ledColor"] == "OFF"
    r = client.post(f"{BASE}/gate/entry-tap", headers=DEVICE, json=tap_body())
    assert r.json()["recommendation"]["slotId"] not in ("F1-A05", "F1-A06")


def test_tc06_prediction_ok_and_invalid_window(client):
    r = client.get(f"{BASE}/ai/predictions/occupancy?fromHour=6&toHour=9", headers=DASH)
    assert r.status_code == 200
    body = r.json()
    assert {p["hour"] for p in body["predictions"]} == {6, 7, 8, 9}
    assert isinstance(body["advisory"], str) and body["advisory"]
    bad = client.get(f"{BASE}/ai/predictions/occupancy?fromHour=9&toHour=6", headers=DASH)
    assert bad.status_code == 400 and bad.json()["code"] == "INVALID_TIME_WINDOW"


def test_tc07_authorization(client):
    assert client.post(f"{BASE}/gate/entry-tap", json=tap_body()).status_code == 401
    wrong = {"X-Device-Key": "salah"}
    assert client.put(f"{BASE}/slots/F1-A01/status", headers=wrong, json=status_body()).status_code == 401
    # endpoint prediksi hanya menerima Bearer, bukan kunci perangkat
    r = client.get(f"{BASE}/ai/predictions/occupancy?fromHour=6&toHour=9", headers=DEVICE)
    assert r.status_code == 401 and r.json()["code"] == "UNAUTHORIZED"
    # okupansi menerima keduanya
    assert client.get(f"{BASE}/occupancy/floors", headers=DEVICE).status_code == 200
    assert client.get(f"{BASE}/occupancy/floors", headers=DASH).status_code == 200


def test_tc08_invalid_status(client):
    r = client.put(f"{BASE}/slots/F1-A01/status", headers=DEVICE, json=status_body("BROKEN"))
    assert r.status_code == 400 and r.json()["code"] == "INVALID_STATUS"


def test_tc09_recommendation_failure_keeps_barrier_open(client):
    client.post(f"{BASE}/dev/fault/recommendation?enabled=true", headers=DEVICE)
    r = client.post(f"{BASE}/gate/entry-tap", headers=DEVICE, json=tap_body())
    assert r.status_code == 500
    body = r.json()
    assert body["code"] == "RECOMMENDATION_FAILED"
    assert body["gateAction"] == "OPEN_BARRIER"
    assert "Lantai 1" in body["displayMessage"] and len(body["floors"]) == 2
    client.post(f"{BASE}/dev/fault/recommendation?enabled=false", headers=DEVICE)
    assert client.post(f"{BASE}/gate/entry-tap", headers=DEVICE, json=tap_body()).status_code == 200


def test_unknown_slot_and_bad_payload(client):
    assert client.put(f"{BASE}/slots/F9-A99/status", headers=DEVICE, json=status_body()).status_code == 404
    r = client.put(f"{BASE}/slots/F1-A01/status", headers=DEVICE, json={"status": "OCCUPIED"})
    assert r.status_code == 400 and r.json()["code"] == "INVALID_REQUEST"


def test_consecutive_taps_get_different_slots(client):
    a = client.post(f"{BASE}/gate/entry-tap", headers=DEVICE, json=tap_body()).json()["recommendation"]
    b = client.post(f"{BASE}/gate/entry-tap", headers=DEVICE, json=tap_body()).json()["recommendation"]
    assert a["slotId"] != b["slotId"]


def test_default_floors_two_floors_upper_closed(client):
    floors = client.get(f"{BASE}/occupancy/floors", headers=DASH).json()["floors"]
    assert [f["floorNumber"] for f in floors] == [1, 2]
    assert floors[0]["isOpen"] and not floors[1]["isOpen"]
    scenario(client, "peak_hour")
    assert floor(client, 2)["isOpen"]
