from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import ai_adapter, db, services
from ..auth import require_device
from ..errors import ApiError, error_body
from ..util import iso, now

router = APIRouter()


class EntryTap(BaseModel):
    gateId: str
    cardId: str
    vehicleType: str = "MOTORCYCLE"
    tapTime: str


def _availability_message(floors: list[dict]) -> str:
    parts = [f"Lantai {f['floorNumber']}: {f['available']} tersedia" for f in floors if f["isOpen"]]
    return " | ".join(parts)


def _candidate_slots(exclude_recommended: bool, at) -> list[dict]:
    with db.lock:
        rows = db.conn().execute(
            "SELECT slot_id, floor_number, status, distance, recommended_at FROM slots"
        ).fetchall()
    return [
        {
            "slotId": r["slot_id"],
            "floorNumber": r["floor_number"],
            "status": r["status"],
            "distance": r["distance"],
        }
        for r in rows
        if not (exclude_recommended and services.recommended_active(r["recommended_at"], at))
    ]


@router.post("/gate/entry-tap", tags=["gate"], dependencies=[Depends(require_device)])
def entry_tap(body: EntryTap):
    """Validasi kartu, catat masuk, minta rekomendasi lantai dan slot, lalu buka palang."""
    at = now()
    with db.lock:
        c = db.conn()
        if c.execute("SELECT 1 FROM cards WHERE card_id=?", (body.cardId,)).fetchone() is None:
            raise ApiError(400, "INVALID_CARD", "Kartu tidak terdaftar; palang tidak dibuka")

    services.refresh(at)
    floors = services.floor_summary()
    floor_cfg = [{"floorNumber": f["floorNumber"], "isOpen": f["isOpen"], "total": f["total"]} for f in floors]

    try:
        if db.state["fail_recommendation"]:
            raise RuntimeError("kegagalan modul AI disimulasikan (flag uji)")
        # Hindari slot yang baru direkomendasikan ke pengemudi lain; bila habis, boleh dipakai lagi.
        recommendation = ai_adapter.recommend_slot(_candidate_slots(True, at), floor_cfg)
        if recommendation is None:
            recommendation = ai_adapter.recommend_slot(_candidate_slots(False, at), floor_cfg)
    except Exception:
        # Kartu valid tetapi rekomendasi gagal: palang TETAP terbuka, tampilkan ketersediaan per lantai.
        _record_entry(body, None, at)
        return JSONResponse(
            status_code=500,
            content=error_body(
                500,
                "RECOMMENDATION_FAILED",
                "Rekomendasi gagal; palang tetap dibuka",
                {
                    "gateAction": "OPEN_BARRIER",
                    "displayMessage": "Silakan masuk. " + _availability_message(floors),
                    "floors": floors,
                },
            ),
        )

    if recommendation is None:
        message = "Parkir penuh. " + _availability_message(floors)
    else:
        message = f"Lantai {recommendation['floorNumber']} - Slot {recommendation['slotId']}"
        with db.lock:
            db.conn().execute(
                "UPDATE slots SET recommended_at=?, led_color='YELLOW' WHERE slot_id=? AND status='AVAILABLE'",
                (iso(at), recommendation["slotId"]),
            )
            db.conn().commit()
    _record_entry(body, recommendation, at)
    return {"recommendation": recommendation, "gateAction": "OPEN_BARRIER", "displayMessage": message}


def _record_entry(body: EntryTap, recommendation: dict | None, at) -> None:
    with db.lock:
        c = db.conn()
        c.execute(
            "INSERT INTO entries (card_id, gate_id, vehicle_type, tap_time, floor_number, slot_id, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                body.cardId,
                body.gateId,
                body.vehicleType,
                body.tapTime,
                recommendation["floorNumber"] if recommendation else None,
                recommendation["slotId"] if recommendation else None,
                iso(at),
            ),
        )
        c.commit()
