"""TC-04 - Motor parkir lalu keluar.

Langkah: PUT OCCUPIED lalu AVAILABLE pada satu slot.
Diharapkan: LED merah lalu hijau; `available` lantai itu berkurang lalu kembali
di GET /occupancy/floors.

Contoh: python -m simulator.scenarios.tc04_park_and_leave --slot F1-A05
"""
import sys

from simulator.scenarios.common import EvidenceLog, base_parser, find_floor, find_slot, load_scenario
from simulator.sensor_sim import ApiClient, ApiUnavailable, LedPanel, SensorSimulator, parse_slot_id


def panel_text(sim: SensorSimulator, api: ApiClient) -> str:
    """Gambar panel LED terkini (dari GET /slots) untuk disimpan di log."""
    sim.panel.sync_from_backend(api)
    return sim.panel.render()


def run(api: ApiClient, log: EvidenceLog, slot_id: str) -> None:
    floor, _ = parse_slot_id(slot_id)
    sim = SensorSimulator(api, LedPanel(use_color=False), on_event=log.write)

    load_scenario(api, log, "reset")

    log.step("GET /occupancy/floors (kondisi awal)")
    code, before = api.get_floors()
    log.http("GET /occupancy/floors", code, before)
    f0 = find_floor(before, floor)
    log.write(f"Lantai {floor} awal: available={f0.get('available')} occupied={f0.get('occupied')}")

    # 1) Motor parkir: sensor membaca 15 cm (< 30 cm)
    log.step(f"PUT /slots/{slot_id}/status jarak 15 cm (motor parkir)")
    code, body = sim.report(slot_id, 15.0)
    log.http(f"PUT /slots/{slot_id}/status", code, body)
    log.check("PUT OCCUPIED -> 200", code == 200, f"HTTP {code}")
    log.check("currentStatus OCCUPIED", body.get("currentStatus") == "OCCUPIED", str(body.get("currentStatus")))
    log.check("ledCommand.color RED", body.get("ledCommand", {}).get("color") == "RED",
              str(body.get("ledCommand")))

    code, slots = api.get_slots()
    s = find_slot(slots, slot_id)
    log.http(f"GET /slots ({slot_id})", code, s)
    log.check("GET /slots: LED merah", s.get("ledColor") == "RED" and s.get("status") == "OCCUPIED",
              f"status={s.get('status')} ledColor={s.get('ledColor')}")

    code, mid = api.get_floors()
    f1 = find_floor(mid, floor)
    log.http("GET /occupancy/floors", code, f1)
    log.check(f"available lantai {floor} berkurang 1", f1.get("available") == f0.get("available", 0) - 1,
              f"{f0.get('available')} -> {f1.get('available')}")
    log.check(f"occupied lantai {floor} bertambah 1", f1.get("occupied") == f0.get("occupied", 0) + 1,
              f"{f0.get('occupied')} -> {f1.get('occupied')}")
    log.write("Panel LED:\n" + panel_text(sim, api))

    # 2) Motor keluar: sensor membaca 150 cm (kosong)
    log.step(f"PUT /slots/{slot_id}/status jarak 150 cm (motor keluar)")
    code, body = sim.report(slot_id, 150.0)
    log.http(f"PUT /slots/{slot_id}/status", code, body)
    log.check("PUT AVAILABLE -> 200", code == 200, f"HTTP {code}")
    log.check("ledCommand.color GREEN", body.get("ledCommand", {}).get("color") == "GREEN",
              str(body.get("ledCommand")))

    code, slots = api.get_slots()
    s = find_slot(slots, slot_id)
    log.http(f"GET /slots ({slot_id})", code, s)
    log.check("GET /slots: LED hijau", s.get("ledColor") == "GREEN" and s.get("status") == "AVAILABLE",
              f"status={s.get('status')} ledColor={s.get('ledColor')}")

    code, after = api.get_floors()
    f2 = find_floor(after, floor)
    log.http("GET /occupancy/floors", code, f2)
    log.check(f"available lantai {floor} kembali", f2.get("available") == f0.get("available"),
              f"{f1.get('available')} -> {f2.get('available')}")
    log.write("Panel LED:\n" + panel_text(sim, api))


def main(argv=None) -> int:
    p = base_parser("TC-04: motor parkir lalu keluar")
    p.add_argument("--slot", default="F1-A05", help="slot uji di lantai terbuka (bawaan F1-A05)")
    args = p.parse_args(argv)
    log = EvidenceLog("TC-04", "Motor parkir lalu keluar", args.evidence_dir, base_url=args.url)
    try:
        run(ApiClient(args.url, args.key), log, args.slot.upper())
    except ApiUnavailable as exc:
        log.check("backend dapat dihubungi", False, str(exc))
    return log.finish()


if __name__ == "__main__":
    sys.exit(main())
