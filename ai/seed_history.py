# pembuatan data riwayat parkir untuk simulasi (14 hari kerja x 24 jam x 2 lantai)
#
# run dengan: python -m ai.seed_history
import json
import random
from datetime import date, timedelta
from pathlib import Path

HISTORY_PATH = Path(__file__).with_name("history.json")
DAYS = 14
START_DATE = date(2026, 11, 2)  # hari Senin
SEED = 42

# pola lantai 1 di hari kerja tiap jam (persen): naik jam 06.30-09.00, penuh sekitar 07.30-11.00
WEEKDAY_FLOOR1 = [5, 4, 4, 4, 5, 6, 20, 70, 95, 98, 97, 90,
                  82, 78, 72, 65, 55, 40, 28, 18, 12, 9, 7, 6]


def generate_history(days=DAYS, seed=SEED):
    rng = random.Random(seed)  # seed tetap supaya hasilnya selalu sama
    rows = []
    day = START_DATE - timedelta(days=1)
    for _ in range(days):
        # hanya hari kerja (Senin-Jumat) karena prediksi ini untuk hari kuliah
        day += timedelta(days=1)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        for hour in range(24):
            base1 = WEEKDAY_FLOOR1[hour]
            floor1 = base1 + rng.uniform(-4, 4)
            # lantai 2 baru terisi setelah lantai 1 hampir penuh (di atas 80%)
            base2 = max(0.0, base1 - 80) * 2.5
            floor2 = base2 + rng.uniform(-3, 3) if base2 > 0 else 0.0
            for floor_number, value in ((1, floor1), (2, floor2)):
                rows.append({
                    "date": day.isoformat(),
                    "hour": hour,
                    "floorNumber": floor_number,
                    "occupancyPercent": round(max(0.0, min(100.0, value)), 1),
                })
    return rows


def save_history(path=HISTORY_PATH):
    rows = generate_history()
    # satu data per baris supaya mudah dibaca
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text("[\n" + ",\n".join(lines) + "\n]\n", encoding="utf-8")
    return rows


def load_history():
    # baca ai/history.json, kalau belum ada, dibuat otomatis
    if not HISTORY_PATH.exists():
        return save_history()
    return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    data = save_history()
    print(f"Tersimpan {len(data)} baris ke {HISTORY_PATH}")
