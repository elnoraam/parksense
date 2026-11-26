"""TC-05 - Sensor bermasalah.

Langkah: sensor berhenti melapor > 60 dtk, atau mengirim 500 cm.
Diharapkan: slot UNKNOWN, LED OFF, keluar dari rekomendasi, dihitung terpisah
(`unknown`) di GET /occupancy/floors. Peringatan dashboard membaca data yang
sama dari GET /slots (tangkapan layarnya diambil dari sisi dashboard).

Varian (--mode):
  glitch    sensor mengirim 500 cm (cepat)
  scenario  POST /dev/scenario/sensor_stale (cepat)
  stale     sensor sungguh berhenti; heartbeat slot lain tetap jalan (menunggu > STALE_SECONDS)
  all       ketiganya (bawaan)

Contoh: python -m simulator.scenarios.tc05_sensor_fault --mode glitch
"""
import sys
import time

from simulator import config
from simulator.scenarios.common import EvidenceLog, base_parser, find_floor, find_slot, load_scenario
from simulator.sensor_sim import ApiClient, ApiUnavailable, LedPanel, SensorSimulator, parse_slot_id


def check_unknown_slot(api, log, slot_id: str) -> None:
    """Cek GET /slots: UNKNOWN + LED OFF, dan GET /occupancy/floors menghitungnya di `unknown`."""
    code, slots = api.get_slots()
    s = find_slot(slots, slot_id)
    log.http(f"GET /slots ({slot_id})", code, s)
    log.check(f"{slot_id} status UNKNOWN", s.get("status") == "UNKNOWN", str(s.get("status")))
    log.check(f"{slot_id} LED OFF", s.get("ledColor") == "OFF", str(s.get("ledColor")))
    unknown_ids = [x["slotId"] for x in slots.get("slots", []) if x["status"] == "UNKNOWN"]

    floor, _ = parse_slot_id(slot_id)
    code, floors = api.get_floors()
    log.http("GET /occupancy/floors", code, floors)
    f = find_floor(floors, floor)
    log.check(f"lantai {floor} menghitung unknown terpisah", f.get("unknown", 0) >= 1,
              f"unknown={f.get('unknown')}")
    total_unknown = sum(x.get("unknown", 0) for x in floors.get("floors", []))
    log.check("jumlah unknown = jumlah slot UNKNOWN di GET /slots", total_unknown == len(unknown_ids),
              f"{total_unknown} vs {len(unknown_ids)}")
    log.check("available+occupied+unknown = total",
              all(x["available"] + x["occupied"] + x["unknown"] == x["total"] for x in floors.get("floors", [])))


def check_not_recommended(api, log, bad_slots: set, expected: str | None = None) -> None:
    """Tap kartu valid: slot UNKNOWN tidak boleh direkomendasikan."""
    log.step("POST /gate/entry-tap (kartu valid)")
    code, body = api.entry_tap()
    log.http("POST /gate/entry-tap", code, body)
    rec = (body.get("recommendation") or {}).get("slotId") if code == 200 else None
    log.check("slot bermasalah tidak direkomendasikan", rec not in bad_slots, f"rekomendasi={rec}")
    if expected:
        log.check(f"rekomendasi jatuh ke satu-satunya slot sehat ({expected})", rec == expected,
                  f"rekomendasi={rec}")


def run_glitch(api, log) -> None:
    """all_full lalu satu slot dikosongkan (sehat) dan satu slot glitch 500 cm.

    Hanya ada satu slot AVAILABLE yang sehat, jadi rekomendasi harus ke sana
    dan tidak pernah ke slot UNKNOWN.
    """
    log.write("--- Varian glitch: sensor mengirim 500 cm ---")
    healthy, broken = "F2-A10", "F2-A11"
    sim = SensorSimulator(api, LedPanel(use_color=False), on_event=log.write)
    load_scenario(api, log, "all_full")

    log.step(f"PUT {healthy} 150 cm (slot sehat, kosong)")
    code, body = sim.report(healthy, 150.0)
    log.http(f"PUT /slots/{healthy}/status", code, body)

    log.step(f"PUT {broken} {config.GLITCH_CM} cm (sensor rusak)")
    code, body = sim.report(broken, float(config.GLITCH_CM))
    log.http(f"PUT /slots/{broken}/status", code, body)
    log.check("PUT 500 cm -> 200", code == 200, f"HTTP {code}")
    log.check("anomaly OUT_OF_RANGE", body.get("anomaly") == "OUT_OF_RANGE", str(body.get("anomaly")))
    log.check("currentStatus UNKNOWN", body.get("currentStatus") == "UNKNOWN", str(body.get("currentStatus")))
    log.check("ledCommand.color OFF", body.get("ledCommand", {}).get("color") == "OFF", str(body.get("ledCommand")))

    check_unknown_slot(api, log, broken)
    check_not_recommended(api, log, {broken}, expected=healthy)


def run_scenario_stale(api, log) -> None:
    """Pakai skenario backend `sensor_stale` (slot basi disiapkan backend)."""
    log.write("--- Varian scenario: POST /dev/scenario/sensor_stale ---")
    load_scenario(api, log, "sensor_stale")
    code, slots = api.get_slots()
    unknown = [s for s in slots.get("slots", []) if s["status"] == "UNKNOWN"]
    log.http("GET /slots (hanya UNKNOWN)", code, unknown)
    log.check("ada slot UNKNOWN setelah sensor_stale", len(unknown) >= 1, f"{len(unknown)} slot")
    log.check("semua slot UNKNOWN ber-LED OFF", all(s["ledColor"] == "OFF" for s in unknown))
    if unknown:
        check_unknown_slot(api, log, unknown[0]["slotId"])
    check_not_recommended(api, log, {s["slotId"] for s in unknown})


def run_real_stale(api, log, wait: float, heartbeat: float) -> None:
    """Sensor sungguh berhenti melapor: slot target di-`stop`, slot pembanding tetap di-heartbeat."""
    log.write("--- Varian stale: sensor berhenti melapor ---")
    target, control = "F1-A07", "F1-A08"
    sim = SensorSimulator(api, LedPanel(use_color=False), heartbeat_seconds=heartbeat, on_event=log.write)
    load_scenario(api, log, "reset")

    log.step(f"Sensor {target} dan {control} melapor terisi")
    sim.set_state(target, "occupied")
    sim.set_state(control, "occupied")
    log.step(f"stop {target}; heartbeat tiap {heartbeat:g} dtk tetap berjalan untuk {control}")
    sim.stop(target)
    sim.start_heartbeat()
    log.step(f"Menunggu {wait:g} dtk (> STALE_SECONDS={config.STALE_SECONDS})")
    try:
        time.sleep(wait)
    finally:
        sim.stop_heartbeat()
    log.write(f"Heartbeat terkirim {sim.heartbeat_count} putaran selama menunggu")

    check_unknown_slot(api, log, target)
    code, slots = api.get_slots()
    c = find_slot(slots, control)
    log.http(f"GET /slots ({control})", code, c)
    log.check(f"{control} tetap OCCUPIED berkat heartbeat", c.get("status") == "OCCUPIED" and c.get("ledColor") == "RED",
              f"status={c.get('status')} ledColor={c.get('ledColor')}")
    check_not_recommended(api, log, {target})


def main(argv=None) -> int:
    p = base_parser("TC-05: sensor bermasalah -> UNKNOWN + LED OFF")
    p.add_argument("--mode", choices=["glitch", "scenario", "stale", "all"], default="all")
    p.add_argument("--wait", type=float, default=config.STALE_SECONDS + 5,
                   help="lama menunggu varian stale (bawaan STALE_SECONDS + 5)")
    p.add_argument("--heartbeat", type=float, default=config.HEARTBEAT_SECONDS,
                   help="interval heartbeat slot pembanding (bawaan %(default)s)")
    args = p.parse_args(argv)
    api = ApiClient(args.url, args.key)
    log = EvidenceLog("TC-05", f"Sensor bermasalah (mode {args.mode})", args.evidence_dir, base_url=args.url)
    try:
        if args.mode in ("glitch", "all"):
            run_glitch(api, log)
        if args.mode in ("scenario", "all"):
            run_scenario_stale(api, log)
        if args.mode in ("stale", "all"):
            run_real_stale(api, log, args.wait, args.heartbeat)
    except ApiUnavailable as exc:
        log.check("backend dapat dihubungi", False, str(exc))
    return log.finish()


if __name__ == "__main__":
    sys.exit(main())
