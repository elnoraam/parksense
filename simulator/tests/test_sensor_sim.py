"""Uji paket simulator terhadap backend tiruan (tanpa jaringan, tanpa backend asli)."""
import time

import pytest

from simulator import config
from simulator import sensor_sim as sim_mod
from simulator.scenarios import run_scenario, tc04_park_and_leave, tc05_sensor_fault
from simulator.tests.mock_backend import start_mock


@pytest.fixture
def mock():
    server, state, url = start_mock(0, stale_seconds=1.0)
    yield state, url
    server.shutdown()


@pytest.fixture
def sim(mock):
    _, url = mock
    s = sim_mod.SensorSimulator(sim_mod.ApiClient(url), sim_mod.LedPanel(use_color=False), heartbeat_seconds=0.2)
    yield s
    s.stop_heartbeat()


# --- logika murni -------------------------------------------------------------
def test_status_from_distance_threshold():
    assert sim_mod.status_from_distance(29.9) == "OCCUPIED"
    assert sim_mod.status_from_distance(30) == "AVAILABLE"


def test_reasonable_distances():
    for _ in range(100):
        assert 10 <= sim_mod.distance_for("occupied") <= 25
        assert 80 <= sim_mod.distance_for("free") <= 200


def test_slot_ids_and_gateway():
    ids = sim_mod.all_slot_ids()
    assert len(ids) == 40 and ids[0] == "F1-A01" and ids[-1] == "F2-A20"
    assert sim_mod.gateway_id_for("F2-A17") == "ESP32-GW-F2"
    with pytest.raises(ValueError):
        sim_mod.parse_slot_id("F3A1")


def test_payload_matches_contract():
    p = sim_mod.build_payload("F2-A17", 15.0)
    assert set(p) == {"gatewayId", "sensorType", "rawSensorValue", "unit", "status", "measuredAt"}
    assert p["gatewayId"] == "ESP32-GW-F2" and p["unit"] == "cm" and p["status"] == "OCCUPIED"
    assert p["measuredAt"].endswith("+07:00")


# --- terhadap backend tiruan --------------------------------------------------
def test_set_occupied_then_free_updates_led(sim, mock):
    state, _ = mock
    sim.set_state("F1-A05", "occupied")
    assert sim.panel.colors["F1-A05"] == "RED"
    sim.set_state("F1-A05", "free")
    assert sim.panel.colors["F1-A05"] == "GREEN"
    assert state.put_log[-1]["gatewayId"] == "ESP32-GW-F1"


def test_glitch_gives_unknown_and_led_off(sim):
    code, body = sim.glitch("F2-A17")
    assert code == 200 and body["anomaly"] == "OUT_OF_RANGE"
    assert sim.panel.colors["F2-A17"] == "OFF"


def test_heartbeat_resends_and_stop_halts_it(sim, mock):
    state, _ = mock
    sim.set_state("F1-A01", "occupied")
    sim.set_state("F1-A02", "occupied")
    sim.stop("F1-A02")
    sim.start_heartbeat()
    time.sleep(1.5)  # > stale_seconds tiruan (1 dtk)
    sim.stop_heartbeat()
    sent = [p["slotId"] for p in state.put_log]
    assert sent.count("F1-A01") >= 3          # dikirim ulang terus
    assert sent.count("F1-A02") == 1          # berhenti setelah stop
    _, slots = sim.api.get_slots()
    by_id = {s["slotId"]: s for s in slots["slots"]}
    assert by_id["F1-A01"]["status"] == "OCCUPIED"
    assert by_id["F1-A02"]["status"] == "UNKNOWN" and by_id["F1-A02"]["ledColor"] == "OFF"


def test_heartbeat_interval_default_is_safe():
    assert config.HEARTBEAT_SECONDS <= 30


def test_adopt_after_scenario(sim):
    sim.api.load_scenario("peak_hour")
    assert sim.adopt_from_backend() == 40
    assert len(sim.occupied_slots()) == 18


def test_auto_traffic_parks_motors(sim):
    sim_mod.random.seed(1)
    sim.api.load_scenario("reset")
    traffic = sim_mod.AutoTraffic(sim, speed=600, start_hour=7, tap=True)
    for _ in range(20):
        traffic.step(0.5)  # 20 x 5 menit simulasi
    assert traffic.arrived > 0
    assert traffic.clock() == "08:40"
    _, floors = sim.api.get_floors()
    assert sum(f["occupied"] for f in floors["floors"]) == traffic.arrived - traffic.departed


def test_unreachable_backend_raises():
    api = sim_mod.ApiClient("http://127.0.0.1:9/api/v1")
    with pytest.raises(sim_mod.ApiUnavailable):
        api.get_slots()


# --- runner skenario ----------------------------------------------------------
def test_tc04_runner_passes(mock, tmp_path):
    _, url = mock
    assert tc04_park_and_leave.main(["--url", url, "--evidence-dir", str(tmp_path)]) == 0
    log = next(tmp_path.glob("TC-04_*.log")).read_text(encoding="utf-8")
    assert "HASIL    TC-04: LULUS" in log


def test_tc05_runner_passes_all_modes(mock, tmp_path):
    _, url = mock
    rc = tc05_sensor_fault.main(["--url", url, "--evidence-dir", str(tmp_path),
                                 "--mode", "all", "--wait", "1.5", "--heartbeat", "0.3"])
    assert rc == 0
    log = next(tmp_path.glob("TC-05_*.log")).read_text(encoding="utf-8")
    assert "GAGAL    " not in log and "TC-05: LULUS" in log


def test_scenario_runner_logs(mock, tmp_path):
    _, url = mock
    assert run_scenario.main(["peak_hour", "--url", url, "--evidence-dir", str(tmp_path)]) == 0
    assert list(tmp_path.glob("scenario-peak_hour_*.log"))


def test_runner_reports_failure_when_backend_down(tmp_path):
    rc = tc04_park_and_leave.main(["--url", "http://127.0.0.1:9/api/v1", "--evidence-dir", str(tmp_path)])
    assert rc == 1
