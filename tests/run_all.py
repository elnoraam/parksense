"""Menjalankan ulang TC-01 s.d. TC-09 terhadap backend yang sedang berjalan.

Dipakai saat demo dan untuk mengumpulkan bukti uji. Berbeda dengan
tests/api_tests (pytest + database di memori), skrip ini memanggil server
sungguhan lewat HTTP, jadi backend harus dinyalakan dulu:

    python -m uvicorn backend.main:app --port 8000
    python tests/run_all.py            # semua TC
    python tests/run_all.py TC-01 TC-06  # hanya TC tertentu

Hasil (Lulus/Gagal + respons JSON) dicetak ke layar dan disimpan ke
tests/evidence/run_all_<waktu>.log.

Catatan: skrip ini mengubah data di database lokal (memakai /dev/scenario),
dan di akhir selalu memulihkan kondisi dengan scenario `reset` serta
mematikan fault rekomendasi.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# --- Konfigurasi (satu tempat) ---
# PARKSENSE_URL sama dengan yang dipakai simulator; boleh dengan atau tanpa /api/v1
_url = os.environ.get("PARKSENSE_URL", "http://127.0.0.1:8000").rstrip("/")
BASE = _url if _url.endswith("/api/v1") else _url + "/api/v1"
DEVICE = {"X-Device-Key": "parksense-dev-key"}
DASH = {"Authorization": "Bearer dev-dashboard-token"}
VALID_CARD = "RFID-04A1B7C2"
INVALID_CARD = "RFID-TIDAK-ADA"

EVIDENCE_DIR = Path(__file__).resolve().parent / "evidence"
log_lines = []


def log(text=""):
    print(text)
    log_lines.append(text)


def call(method, path, headers=None, body=None):
    """Kirim request HTTP, kembalikan (status_code, json_body)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:  # 4xx/5xx tetap dibaca isinya
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw.decode(errors="replace")


def show(label, status, body):
    log(f"  {label} -> {status} {json.dumps(body, ensure_ascii=False)}")


# --- Payload sama dengan tests/api_tests/conftest.py ---
def tap_body(card=VALID_CARD):
    return {"gateId": "GATE-IN-01", "cardId": card, "vehicleType": "MOTORCYCLE",
            "tapTime": datetime.now().astimezone().isoformat(timespec="seconds")}


def status_body(status="OCCUPIED", raw=18.4, floor_no=1):
    return {"gatewayId": f"ESP32-GW-F{floor_no}", "sensorType": "ULTRASONIC", "rawSensorValue": raw,
            "unit": "cm", "status": status,
            "measuredAt": datetime.now().astimezone().isoformat(timespec="seconds")}


def scenario(name):
    status, _ = call("POST", f"/dev/scenario/{name}", DEVICE)
    assert status == 200, f"scenario {name} gagal dimuat ({status})"


def floor(number):
    _, body = call("GET", "/occupancy/floors", DASH)
    return next(f for f in body["floors"] if f["floorNumber"] == number)


def slot(slot_id):
    _, body = call("GET", "/slots", DASH)
    return next(s for s in body["slots"] if s["slotId"] == slot_id)


# --- Kasus uji ---
def tc01():
    scenario("peak_hour")
    status, body = call("POST", "/gate/entry-tap", DEVICE, tap_body())
    show("POST /gate/entry-tap (kartu valid, peak_hour)", status, body)
    assert status == 200
    assert body["gateAction"] == "OPEN_BARRIER"
    assert body["recommendation"]["floorNumber"] == 2, "rekomendasi bukan lantai 2"
    slot_id = body["recommendation"]["slotId"]
    led = slot(slot_id)["ledColor"]
    log(f"  LED {slot_id} = {led}")
    assert led == "YELLOW"


def tc02():
    scenario("all_full")
    status, body = call("POST", "/gate/entry-tap", DEVICE, tap_body())
    show("POST /gate/entry-tap (all_full)", status, body)
    assert status == 200
    assert body["recommendation"] is None
    assert body["gateAction"] == "OPEN_BARRIER"
    assert "penuh" in body["displayMessage"].lower()


def tc03():
    status, body = call("POST", "/gate/entry-tap", DEVICE, tap_body(INVALID_CARD))
    show(f"POST /gate/entry-tap (kartu {INVALID_CARD})", status, body)
    assert status == 400 and body["code"] == "INVALID_CARD"
    assert "gateAction" not in body, "palang tidak boleh dibuka"


def tc04():
    before = floor(2)["available"]
    log(f"  available lantai 2 awal = {before}")
    status, body = call("PUT", "/slots/F2-A17/status", DEVICE, status_body("OCCUPIED", 18.4, floor_no=2))
    show("PUT F2-A17 OCCUPIED", status, body)
    assert status == 200 and body["ledCommand"]["color"] == "RED"
    after_park = floor(2)["available"]
    log(f"  available lantai 2 setelah parkir = {after_park}")
    assert after_park == before - 1
    status, body = call("PUT", "/slots/F2-A17/status", DEVICE, status_body("AVAILABLE", 150, floor_no=2))
    show("PUT F2-A17 AVAILABLE", status, body)
    assert status == 200 and body["ledCommand"]["color"] == "GREEN"
    after_exit = floor(2)["available"]
    log(f"  available lantai 2 setelah keluar = {after_exit}")
    assert after_exit == before


def tc05():
    # (a) nilai sensor di luar rentang 2..400 cm
    unknown_before = floor(1)["unknown"]
    status, body = call("PUT", "/slots/F1-A03/status", DEVICE, status_body("OCCUPIED", 500))
    show("PUT F1-A03 rawSensorValue=500", status, body)
    assert body["currentStatus"] == "UNKNOWN" and body["ledCommand"]["color"] == "OFF"
    assert floor(1)["unknown"] == unknown_before + 1, "UNKNOWN tidak dihitung terpisah"
    # (b) sensor berhenti melapor (basi > 60 detik)
    scenario("sensor_stale")
    f1 = floor(1)
    log(f"  lantai 1 setelah sensor_stale: {json.dumps(f1)}")
    s = slot("F1-A05")
    log(f"  F1-A05 status={s['status']} led={s['ledColor']}")
    assert s["status"] == "UNKNOWN" and s["ledColor"] == "OFF"
    status, body = call("POST", "/gate/entry-tap", DEVICE, tap_body())
    show("POST /gate/entry-tap (setelah sensor_stale)", status, body)
    assert body["recommendation"]["slotId"] not in ("F1-A05", "F1-A06"), "slot UNKNOWN direkomendasikan"


def tc06():
    status, body = call("GET", "/ai/predictions/occupancy?fromHour=6&toHour=9", DASH)
    show("GET predictions 6..9", status, body)
    assert status == 200
    assert {p["hour"] for p in body["predictions"]} == {6, 7, 8, 9}
    assert isinstance(body["advisory"], str) and body["advisory"]
    status, body = call("GET", "/ai/predictions/occupancy?fromHour=9&toHour=6", DASH)
    show("GET predictions 9..6", status, body)
    assert status == 400 and body["code"] == "INVALID_TIME_WINDOW"


def tc07():
    status, body = call("POST", "/gate/entry-tap", None, tap_body())
    show("POST /gate/entry-tap tanpa kunci", status, body)
    assert status == 401
    status, body = call("PUT", "/slots/F1-A01/status", {"X-Device-Key": "salah"}, status_body())
    show("PUT /slots/F1-A01/status kunci salah", status, body)
    assert status == 401
    status, body = call("GET", "/ai/predictions/occupancy?fromHour=6&toHour=9", DEVICE)
    show("GET predictions dengan X-Device-Key (harus Bearer)", status, body)
    assert status == 401


def tc08():
    status, body = call("PUT", "/slots/F1-A01/status", DEVICE, status_body("BROKEN"))
    show("PUT F1-A01 status=BROKEN", status, body)
    assert status == 400 and body["code"] == "INVALID_STATUS"


def tc09():
    call("POST", "/dev/fault/recommendation?enabled=true", DEVICE)
    try:
        status, body = call("POST", "/gate/entry-tap", DEVICE, tap_body())
        show("POST /gate/entry-tap (fault aktif)", status, body)
        assert status == 500 and body["code"] == "RECOMMENDATION_FAILED"
        assert body["gateAction"] == "OPEN_BARRIER", "palang harus tetap terbuka"
        assert len(body["floors"]) == 2, "ringkasan per lantai tidak ada"
    finally:
        # selalu pulihkan, walaupun TC gagal
        call("POST", "/dev/fault/recommendation?enabled=false", DEVICE)
    status, _ = call("POST", "/gate/entry-tap", DEVICE, tap_body())
    log(f"  setelah dipulihkan, tap valid -> {status}")
    assert status == 200


CASES = [
    ("TC-01", "Tap valid jam puncak", tc01),
    ("TC-02", "Semua lantai penuh", tc02),
    ("TC-03", "Kartu tidak valid", tc03),
    ("TC-04", "Motor parkir lalu keluar", tc04),
    ("TC-05", "Sensor bermasalah", tc05),
    ("TC-06", "Prediksi jam puncak", tc06),
    ("TC-07", "Otorisasi", tc07),
    ("TC-08", "Status tidak valid", tc08),
    ("TC-09", "Rekomendasi gagal", tc09),
]


def main():
    wanted = {a.upper() for a in sys.argv[1:]}
    started = datetime.now().astimezone()
    log(f"ParkSense run_all - {started.isoformat(timespec='seconds')} - {BASE}")

    try:
        call("GET", "/occupancy/floors", DASH)
    except urllib.error.URLError:
        print(f"Backend tidak bisa dihubungi di {BASE}. Nyalakan dulu:\n"
              "  python -m uvicorn backend.main:app --port 8000")
        sys.exit(2)

    results = []
    for tc_id, name, fn in CASES:
        if wanted and tc_id not in wanted:
            continue
        log(f"\n[{tc_id}] {name}")
        scenario("reset")  # tiap TC mulai dari kondisi bersih
        try:
            fn()
            results.append((tc_id, "LULUS", ""))
        except AssertionError as e:
            results.append((tc_id, "GAGAL", str(e)))
        except Exception as e:  # galat tak terduga (mis. field hilang)
            results.append((tc_id, "GAGAL", f"{type(e).__name__}: {e}"))
        log(f"  => {results[-1][1]} {results[-1][2]}")

    scenario("reset")  # kembalikan ke kondisi awal setelah selesai

    log("\nRingkasan")
    for tc_id, res, note in results:
        log(f"  {tc_id}: {res}{' - ' + note if note else ''}")
    passed = sum(r == "LULUS" for _, r, _ in results)
    log(f"  {passed}/{len(results)} lulus")

    EVIDENCE_DIR.mkdir(exist_ok=True)
    out = EVIDENCE_DIR / f"run_all_{started.strftime('%Y%m%d-%H%M%S')}.log"
    out.write_text("\n".join(log_lines), encoding="utf-8")
    print(f"\nLog disimpan: {out}")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()