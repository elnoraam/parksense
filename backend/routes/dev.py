"""Endpoint pendukung untuk demo dan pengujian (di luar spesifikasi 2.3)."""
from datetime import timedelta

from fastapi import APIRouter, Depends

from .. import db, services
from ..auth import require_device
from ..errors import ApiError
from ..util import iso, now

router = APIRouter(prefix="/dev", tags=["dev"], dependencies=[Depends(require_device)])

SCENARIOS = ("reset", "peak_hour", "all_full", "sensor_stale")


def _occupy(slot_ids: list[str], last_update: str | None = None) -> None:
    with db.lock:
        c = db.conn()
        for sid in slot_ids:
            c.execute(
                "UPDATE slots SET status='OCCUPIED', led_color='RED', last_update=? WHERE slot_id=?",
                (last_update, sid),
            )
        c.commit()


def _open_floor(floor_number: int) -> None:
    with db.lock:
        db.conn().execute("UPDATE floors SET is_open=1 WHERE floor_number=?", (floor_number,))
        db.conn().commit()


@router.post("/scenario/{name}")
def load_scenario(name: str):
    """reset | peak_hour (lantai 1 hampir penuh, lantai 2 dibuka) | all_full | sensor_stale."""
    if name not in SCENARIOS:
        raise ApiError(404, "SCENARIO_NOT_FOUND", f"skenario harus salah satu dari {', '.join(SCENARIOS)}")
    db.reset_all()
    if name == "peak_hour":
        _open_floor(2)  # lantai atas baru dibuka saat jam puncak
        _occupy([f"F1-A{n:02d}" for n in range(1, 20)] + [f"F2-A{n:02d}" for n in range(1, 5)])
    elif name == "all_full":
        _open_floor(2)
        _occupy([f"F{fl}-A{n:02d}" for fl in db.FLOORS for n in range(1, db.SLOTS_PER_FLOOR + 1)])
    elif name == "sensor_stale":
        old = iso(now() - timedelta(seconds=services.STALE_SECONDS + 600))
        _occupy(["F1-A05", "F1-A06"], last_update=old)
    return {"scenario": name, "applied": True}


@router.post("/fault/recommendation")
def set_recommendation_fault(enabled: bool = True):
    """Paksa modul rekomendasi gagal (untuk TC-09). enabled=false untuk memulihkan."""
    db.state["fail_recommendation"] = enabled
    return {"fault": "recommendation", "enabled": enabled}
