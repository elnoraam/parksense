import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import ai_adapter, db, services
from ..auth import require_any, require_device
from ..errors import ApiError
from ..util import iso, now, parse_iso

router = APIRouter()

VALID_STATUS = ("AVAILABLE", "OCCUPIED", "UNKNOWN")


class SlotStatusUpdate(BaseModel):
    gatewayId: str
    sensorType: str
    rawSensorValue: float
    unit: str = "cm"
    status: str
    measuredAt: str


@router.put("/slots/{slot_id}/status", tags=["slots"], dependencies=[Depends(require_device)])
def update_slot_status(slot_id: str, body: SlotStatusUpdate):
    """Gateway IoT melaporkan status slot; platform memperbarui status dan memicu LED."""
    if body.status not in VALID_STATUS:
        raise ApiError(400, "INVALID_STATUS", f"status harus salah satu dari {', '.join(VALID_STATUS)}")
    try:
        parse_iso(body.measuredAt)
    except ValueError:
        raise ApiError(400, "INVALID_REQUEST", "measuredAt harus berformat ISO 8601, mis. 2026-11-12T07:43:02+07:00")

    at = now()
    with db.lock:
        c = db.conn()
        row = c.execute("SELECT slot_id, recommended_at FROM slots WHERE slot_id=?", (slot_id,)).fetchone()
        if row is None:
            raise ApiError(404, "SLOT_NOT_FOUND", f"slot {slot_id} tidak ditemukan")

        # Pembacaan baru dianggap segar (last_update = sekarang); yang dicek: rentang nilai.
        anomaly = ai_adapter.detect_anomaly(
            {"rawSensorValue": body.rawSensorValue, "unit": body.unit, "status": body.status}, at, at
        )
        status = "UNKNOWN" if anomaly != "OK" else body.status
        # Terisi atau tidak diketahui mengakhiri rekomendasi kuning; kosong mempertahankannya.
        recommended_at = row["recommended_at"] if status == "AVAILABLE" else None
        color = services.led_color(status, recommended_at, at)
        try:
            c.execute(
                "UPDATE slots SET status=?, led_color=?, raw_value=?, last_update=?, recommended_at=? WHERE slot_id=?",
                (status, color, body.rawSensorValue, iso(at), recommended_at, slot_id),
            )
            c.execute(
                "INSERT INTO readings (slot_id, gateway_id, sensor_type, raw_value, unit, status, measured_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (slot_id, body.gatewayId, body.sensorType, body.rawSensorValue, body.unit, body.status, body.measuredAt),
            )
            c.commit()
        except sqlite3.Error:
            c.rollback()
            raise ApiError(500, "DB_UPDATE_FAILED", "gagal menyimpan status slot")

    result = {"slotId": slot_id, "currentStatus": status, "ledCommand": {"color": color, "sent": True}}
    if anomaly != "OK":
        result["anomaly"] = anomaly
    return result


@router.get("/slots", tags=["slots"], dependencies=[Depends(require_any)])
def list_slots():
    """Pendukung (di luar spesifikasi 2.3): semua slot beserta warna LED, untuk peta slot."""
    return {"slots": services.slot_list(), "generatedAt": services.generated_at()}
