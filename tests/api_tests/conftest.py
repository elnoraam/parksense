import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.main import app

DEVICE = {"X-Device-Key": "parksense-dev-key"}
DASH = {"Authorization": "Bearer dev-dashboard-token"}
BASE = "/api/v1"
VALID_CARD = "RFID-04A1B7C2"


@pytest.fixture()
def client():
    db.init(":memory:")  # database baru dan bersih untuk tiap tes
    with TestClient(app) as c:
        yield c


def tap_body(card: str = VALID_CARD) -> dict:
    return {
        "gateId": "GATE-IN-01",
        "cardId": card,
        "vehicleType": "MOTORCYCLE",
        "tapTime": "2026-11-21T07:42:15+07:00",
    }


def status_body(status: str = "OCCUPIED", raw: float = 18.4) -> dict:
    return {
        "gatewayId": "ESP32-GW-F2",
        "sensorType": "ULTRASONIC",
        "rawSensorValue": raw,
        "unit": "cm",
        "status": status,
        "measuredAt": "2026-11-21T07:43:02+07:00",
    }


def floor(client, number: int) -> dict:
    floors = client.get(f"{BASE}/occupancy/floors", headers=DASH).json()["floors"]
    return next(f for f in floors if f["floorNumber"] == number)


def slot(client, slot_id: str) -> dict:
    slots = client.get(f"{BASE}/slots", headers=DASH).json()["slots"]
    return next(s for s in slots if s["slotId"] == slot_id)
