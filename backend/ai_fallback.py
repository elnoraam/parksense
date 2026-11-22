"""Implementasi cadangan modul AI, dipakai bila ai/ belum ada.

Tanda tangan fungsi identik dengan kontrak antarmuka modul AI. Sengaja sederhana dan mudah dijelaskan.
"""
import random
from collections import Counter, defaultdict
from datetime import datetime

LOAD_LIMIT = 0.85       # lantai di atas ini dihindari bila lantai lain masih longgar
W_CAPACITY, W_NEAR = 0.6, 0.4
SENSOR_MIN_CM, SENSOR_MAX_CM = 2, 400
STALE_SECONDS = 60
OCCUPIED_BELOW_CM = 30


def recommend_slot(slots: list[dict], floors: list[dict]) -> dict | None:
    open_floors = {f["floorNumber"]: f for f in floors if f["isOpen"]}
    occupied = Counter(s["floorNumber"] for s in slots if s["status"] == "OCCUPIED")
    load = {fn: occupied[fn] / max(f["total"], 1) for fn, f in open_floors.items()}
    candidates = [s for s in slots if s["status"] == "AVAILABLE" and s["floorNumber"] in open_floors]
    if not candidates:
        return None
    pool = [s for s in candidates if load[s["floorNumber"]] <= LOAD_LIMIT] or candidates

    def score(s: dict) -> float:
        return W_CAPACITY * (1 - load[s["floorNumber"]]) + W_NEAR * (1 - s["distance"])

    best = sorted(pool, key=lambda s: (-score(s), s["slotId"]))[0]
    return {"floorNumber": best["floorNumber"], "slotId": best["slotId"]}


def predict_occupancy(time_window: tuple[int, int], history: list[dict], method: str = "mean") -> list[dict]:
    from_hour, to_hour = time_window
    if not (0 <= from_hour < to_hour <= 23):
        raise ValueError("fromHour harus lebih kecil dari toHour dan berada di 0-23")
    buckets: dict[tuple[int, int], list[float]] = defaultdict(list)
    for r in history:
        buckets[(r["hour"], r["floorNumber"])].append(r["occupancyPercent"])
    floors = sorted({fl for (_, fl) in buckets})
    out = []
    for hour in range(from_hour, to_hour + 1):
        for fl in floors:
            vals = buckets.get((hour, fl), [])
            out.append(
                {
                    "hour": hour,
                    "floorNumber": fl,
                    "predictedOccupancyPercent": round(sum(vals) / len(vals), 1) if vals else 0.0,
                }
            )
    return out


def make_advisory(predictions: list[dict], floors: list[dict]) -> str:
    if not predictions:
        return "Tidak ada data prediksi untuk rentang waktu ini."
    peak = max(predictions, key=lambda p: p["predictedOccupancyPercent"])
    closed = sorted(f["floorNumber"] for f in floors if not f["isOpen"])
    pct = peak["predictedOccupancyPercent"]
    if pct >= LOAD_LIMIT * 100 and closed:
        return (
            f"Lantai {peak['floorNumber']} diperkirakan penuh sekitar pukul {peak['hour']:02d}.00 ({pct:.0f}%). "
            f"Pertimbangkan membuka lantai {closed[0]} lebih awal."
        )
    if pct >= LOAD_LIMIT * 100:
        return (
            f"Lantai {peak['floorNumber']} diperkirakan penuh sekitar pukul {peak['hour']:02d}.00 ({pct:.0f}%) "
            "dan tidak ada lantai cadangan."
        )
    return "Okupansi diperkirakan masih terkendali pada rentang waktu ini."


def detect_anomaly(reading: dict, last_update: datetime | None, now: datetime) -> str:
    value = reading.get("rawSensorValue")
    if value is not None and not (SENSOR_MIN_CM <= value <= SENSOR_MAX_CM):
        return "OUT_OF_RANGE"
    if last_update is not None and (now - last_update).total_seconds() > STALE_SECONDS:
        return "STALE"
    return "OK"


def status_from_distance(cm: float) -> str:
    return "OCCUPIED" if cm < OCCUPIED_BELOW_CM else "AVAILABLE"


def load_history() -> list[dict]:
    """Riwayat okupansi simulasi 14 hari (deterministik) dengan puncak 06.00-09.00."""
    rng = random.Random(42)
    f1 = [2, 2, 2, 2, 3, 8, 28, 62, 88, 95, 96, 94, 90, 80, 70, 60, 50, 40, 25, 15, 10, 6, 4, 3]
    curves = {1: f1, 2: [min(100, max(0, (v - 50) * 1.2)) for v in f1]}
    rows = []
    for day in range(1, 15):
        for hour in range(24):
            for fl, curve in curves.items():
                base = curve[hour]
                noise = rng.uniform(-5, 5) if base > 0 else 0
                rows.append(
                    {
                        "date": f"2026-11-{day:02d}",
                        "hour": hour,
                        "floorNumber": fl,
                        "occupancyPercent": round(min(100, max(0, base + noise)), 1),
                    }
                )
    return rows
