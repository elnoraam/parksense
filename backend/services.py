"""Logika bersama: warna LED, deteksi sensor basi, ringkasan lantai, daftar slot."""
import os
from datetime import datetime

from . import db
from .util import iso, now, parse_iso

# Sensor dianggap basi bila tidak melapor lebih dari ini. Sensor sungguhan mengirim
# heartbeat berkala; simulator harus meniru itu (heartbeat).
STALE_SECONDS = int(os.getenv("STALE_SECONDS", "60"))
# Slot rekomendasi menyala kuning selama ini (rekomendasi bukan reservasi).
RECOMMEND_TTL_SECONDS = int(os.getenv("RECOMMEND_TTL_SECONDS", "120"))


def recommended_active(recommended_at: str | None, at: datetime) -> bool:
    if not recommended_at:
        return False
    return (at - parse_iso(recommended_at)).total_seconds() < RECOMMEND_TTL_SECONDS


def led_color(status: str, recommended_at: str | None, at: datetime) -> str:
    if status == "UNKNOWN":
        return "OFF"
    if status == "OCCUPIED":
        return "RED"
    return "YELLOW" if recommended_active(recommended_at, at) else "GREEN"


def refresh(at: datetime | None = None) -> None:
    """Tandai slot yang sensornya basi sebagai UNKNOWN dan sinkronkan warna LED."""
    at = at or now()
    with db.lock:
        c = db.conn()
        for r in c.execute("SELECT slot_id, status, last_update, recommended_at, led_color FROM slots").fetchall():
            status = r["status"]
            if status != "UNKNOWN" and r["last_update"]:
                if (at - parse_iso(r["last_update"])).total_seconds() > STALE_SECONDS:
                    status = "UNKNOWN"
            color = led_color(status, r["recommended_at"], at)
            if status != r["status"] or color != r["led_color"]:
                c.execute(
                    "UPDATE slots SET status=?, led_color=?, recommended_at=? WHERE slot_id=?",
                    (status, color, None if status == "UNKNOWN" else r["recommended_at"], r["slot_id"]),
                )
        c.commit()


def slot_list() -> list[dict]:
    refresh()
    with db.lock:
        rows = db.conn().execute(
            "SELECT slot_id, floor_number, status, led_color, last_update FROM slots ORDER BY slot_id"
        ).fetchall()
    return [
        {
            "slotId": r["slot_id"],
            "floorNumber": r["floor_number"],
            "status": r["status"],
            "ledColor": r["led_color"],
            "lastUpdate": r["last_update"],
        }
        for r in rows
    ]


def floor_summary() -> list[dict]:
    refresh()
    with db.lock:
        c = db.conn()
        floors = c.execute("SELECT floor_number, is_open, total FROM floors ORDER BY floor_number").fetchall()
        counts = {
            (r["floor_number"], r["status"]): r["n"]
            for r in c.execute("SELECT floor_number, status, COUNT(*) AS n FROM slots GROUP BY floor_number, status")
        }
    return [
        {
            "floorNumber": f["floor_number"],
            "isOpen": bool(f["is_open"]),
            "total": f["total"],
            "available": counts.get((f["floor_number"], "AVAILABLE"), 0),
            "occupied": counts.get((f["floor_number"], "OCCUPIED"), 0),
            "unknown": counts.get((f["floor_number"], "UNKNOWN"), 0),
        }
        for f in floors
    ]


def generated_at() -> str:
    return iso(now())
