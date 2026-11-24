"""Simulator gateway IoT ParkSense (ESP32 + sensor ultrasonik, versi virtual).

Simulator ini berperan sebagai gateway `ESP32-GW-F{lantai}` yang melaporkan
jarak sensor tiap slot ke backend lewat `PUT /slots/{slot_id}/status`, persis
sesuai kontrak AGENTS.md Bagian 4. LED tiap slot ditampilkan sebagai panel
berwarna di terminal dan diperbarui dari `ledCommand` balasan backend.

Mode:
  manual    : konsol interaktif (set/glitch/stop/resume/scenario/panel ...)
  auto      : motor datang/pergi acak mengikuti pola jam puncak (--speed)
  fault     : memicu sensor bermasalah (stop -> STALE, glitch -> 500 cm)
  set       : satu laporan sekali jalan (tanpa heartbeat)
  scenario  : memanggil POST /dev/scenario/{name}
  panel     : menampilkan panel LED dari GET /slots

Contoh:
  python -m simulator.sensor_sim manual
  python -m simulator.sensor_sim auto --speed 60 --tap
  python -m simulator.sensor_sim fault glitch F2-A17
"""
from __future__ import annotations

import argparse
import cmd
import os
import random
import re
import sys
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

import requests

from simulator import config

WIB = timezone(timedelta(hours=7))
SLOT_ID_RE = re.compile(r"^F(\d+)-A(\d{2})$")
SCENARIOS = ("reset", "peak_hour", "all_full", "sensor_stale")
GATE_ID = "GATE-01"
VEHICLE_TYPE = "MOTORCYCLE"
SENSOR_TYPE = "ULTRASONIC"


# ---------------------------------------------------------------------------
# Fungsi bantu kecil
# ---------------------------------------------------------------------------
def now_iso() -> str:
    """Waktu sekarang dalam ISO 8601 dengan zona +07:00 (aturan kontrak)."""
    return datetime.now(WIB).isoformat(timespec="seconds")


def all_slot_ids() -> list[str]:
    """Semua ID slot sesuai seed: F1-A01 .. F2-A20."""
    return [f"F{f}-A{n:02d}" for f in config.FLOORS for n in range(1, config.SLOTS_PER_FLOOR + 1)]


def parse_slot_id(slot_id: str) -> tuple[int, int]:
    """Ubah 'F2-A17' menjadi (2, 17). ValueError bila formatnya salah."""
    match = SLOT_ID_RE.match(slot_id.strip().upper())
    if not match:
        raise ValueError(f"ID slot '{slot_id}' tidak valid. Format: F<lantai>-A<01..20>, contoh F2-A17")
    return int(match.group(1)), int(match.group(2))


def gateway_id_for(slot_id: str) -> str:
    """Satu gateway per lantai: ESP32-GW-F1, ESP32-GW-F2."""
    floor, _ = parse_slot_id(slot_id)
    return f"ESP32-GW-F{floor}"


def status_from_distance(cm: float) -> str:
    """Logika gateway: jarak < 30 cm berarti ada motor (OCCUPIED).

    Gateway tidak memeriksa rentang 2..400 cm; nilai rusak tetap dikirim apa
    adanya supaya deteksi anomali di backend yang menandai slot UNKNOWN.
    """
    return "OCCUPIED" if cm < config.OCCUPIED_THRESHOLD_CM else "AVAILABLE"


def distance_for(state: str) -> float:
    """Jarak wajar: terisi 10-25 cm, kosong 80-200 cm."""
    if state == "occupied":
        return round(random.uniform(10, 25), 1)
    if state == "free":
        return round(random.uniform(80, 200), 1)
    raise ValueError("Keadaan harus 'occupied' atau 'free'")


def build_payload(slot_id: str, cm: float) -> dict:
    """Payload PUT /slots/{id}/status persis kontrak (camelCase)."""
    return {
        "gatewayId": gateway_id_for(slot_id),
        "sensorType": SENSOR_TYPE,
        "rawSensorValue": cm,
        "unit": "cm",
        "status": status_from_distance(cm),
        "measuredAt": now_iso(),
    }


# ---------------------------------------------------------------------------
# Klien REST API
# ---------------------------------------------------------------------------
class ApiUnavailable(Exception):
    """Backend tidak bisa dihubungi."""


class ApiClient:
    """Pembungkus tipis requests; semua panggilan memakai X-Device-Key."""

    def __init__(self, base_url: str = config.BASE_URL, device_key: str = config.DEVICE_KEY):
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-Device-Key": device_key}

    def _call(self, method: str, path: str, **kwargs) -> tuple[int, dict]:
        url = f"{self.base_url}{path}"
        try:
            resp = requests.request(method, url, headers=self.headers, timeout=config.HTTP_TIMEOUT, **kwargs)
        except requests.RequestException as exc:
            raise ApiUnavailable(f"Backend tidak bisa dihubungi di {self.base_url} ({exc.__class__.__name__})") from exc
        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text}
        return resp.status_code, body

    def put_status(self, slot_id: str, payload: dict):
        return self._call("PUT", f"/slots/{slot_id}/status", json=payload)

    def get_slots(self):
        return self._call("GET", "/slots")

    def get_floors(self):
        return self._call("GET", "/occupancy/floors")

    def load_scenario(self, name: str):
        return self._call("POST", f"/dev/scenario/{name}")

    def entry_tap(self, card_id: str = config.VALID_CARD):
        payload = {"gateId": GATE_ID, "cardId": card_id, "vehicleType": VEHICLE_TYPE, "tapTime": now_iso()}
        return self._call("POST", "/gate/entry-tap", json=payload)


def error_text(code: int, body: dict) -> str:
    """Format galat seragam backend: {status, code, message}."""
    return f"HTTP {code} {body.get('code', '')}: {body.get('message', body)}"


# ---------------------------------------------------------------------------
# Panel LED virtual
# ---------------------------------------------------------------------------
# Warna latar ANSI per warna LED. OFF = abu-abu.
ANSI = {
    "GREEN": "\033[42;30m",
    "RED": "\033[41;97m",
    "YELLOW": "\033[43;30m",
    "OFF": "\033[100;37m",
}
SHORT = {"GREEN": "G", "RED": "R", "YELLOW": "Y", "OFF": "-"}
RESET = "\033[0m"
DIM = "\033[2m"


def enable_windows_ansi() -> None:
    """Terminal Windows 10+ butuh 'dibangunkan' agar kode warna ANSI tampil."""
    if os.name == "nt":
        os.system("")


class LedPanel:
    """Menyimpan warna LED tiap slot dan menggambarnya sebagai grid 2 x 20."""

    def __init__(self, use_color: bool = True):
        self.use_color = use_color
        self.colors = {slot: "OFF" for slot in all_slot_ids()}
        self.floor_open = {f: f == 1 for f in config.FLOORS}  # bawaan seed: lantai 1 buka
        self.lock = threading.Lock()

    def set(self, slot_id: str, color: str) -> None:
        with self.lock:
            self.colors[slot_id] = color if color in ANSI else "OFF"

    def sync_from_backend(self, api: ApiClient) -> bool:
        """Ambil warna terkini dari GET /slots (termasuk kuning dari tap gerbang)."""
        try:
            code, body = api.get_slots()
            if code == 200:
                for s in body.get("slots", []):
                    self.set(s["slotId"], s.get("ledColor", "OFF"))
            fcode, fbody = api.get_floors()
            if fcode == 200:
                for f in fbody.get("floors", []):
                    self.floor_open[f["floorNumber"]] = bool(f.get("isOpen"))
            return code == 200
        except ApiUnavailable:
            return False

    def _cell(self, slot_id: str, color: str) -> str:
        label = slot_id.split("-")[1]  # "A17"
        if self.use_color:
            return f"{ANSI[color]} {label} {RESET}"
        return f"{label}:{SHORT[color]}"

    def render(self) -> str:
        lines = []
        with self.lock:
            for floor in config.FLOORS:
                is_open = self.floor_open.get(floor, True)
                tag = "BUKA" if is_open else "TUTUP"
                title = f"Lantai {floor} [{tag}]"
                lines.append(f"{DIM}{title}{RESET}" if (self.use_color and not is_open) else title)
                ids = [f"F{floor}-A{n:02d}" for n in range(1, config.SLOTS_PER_FLOOR + 1)]
                for row in (ids[:10], ids[10:]):
                    lines.append("  " + " ".join(self._cell(s, self.colors[s]) for s in row))
            legend = ("hijau=AVAILABLE  merah=OCCUPIED  kuning=rekomendasi  abu=UNKNOWN/OFF"
                      if self.use_color else "G=AVAILABLE R=OCCUPIED Y=rekomendasi -=UNKNOWN/OFF")
            lines.append(f"  Keterangan: {legend}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Inti simulator: laporan sensor + heartbeat
# ---------------------------------------------------------------------------
class SensorSimulator:
    """Gateway virtual: menyimpan bacaan terakhir tiap slot dan mengirimnya.

    Heartbeat: backend menandai slot UNKNOWN bila tidak ada laporan > 60 detik,
    jadi thread latar mengirim ulang bacaan terakhir tiap HEARTBEAT_SECONDS
    (<= 30 dtk) untuk slot yang pernah melapor. `stop` mengeluarkan slot dari
    heartbeat, itulah yang memicu STALE di TC-05.
    """

    def __init__(self, api: ApiClient | None = None, panel: LedPanel | None = None,
                 heartbeat_seconds: float = config.HEARTBEAT_SECONDS, on_event=None):
        self.api = api or ApiClient()
        self.panel = panel or LedPanel()
        self.heartbeat_seconds = heartbeat_seconds
        self.readings: dict[str, float] = {}      # bacaan terakhir (cm) per slot
        self.heartbeat_slots: set[str] = set()    # slot yang masih "hidup"
        self.lock = threading.Lock()
        self.events: deque[str] = deque(maxlen=200)
        self.on_event = on_event
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.heartbeat_count = 0

    # --- pencatatan ---------------------------------------------------------
    def log(self, message: str) -> None:
        line = f"[{datetime.now(WIB).strftime('%H:%M:%S')}] {message}"
        self.events.append(line)
        if self.on_event:
            self.on_event(line)

    # --- laporan sensor ------------------------------------------------------
    def report(self, slot_id: str, cm: float, quiet: bool = False):
        """Kirim satu bacaan sensor ke backend dan perbarui LED dari ledCommand.

        Mengembalikan (kode_http, body). Melempar ApiUnavailable bila backend mati.
        """
        slot_id = slot_id.strip().upper()
        parse_slot_id(slot_id)
        payload = build_payload(slot_id, cm)
        code, body = self.api.put_status(slot_id, payload)
        if code == 200:
            color = body.get("ledCommand", {}).get("color", "OFF")
            self.panel.set(slot_id, color)
            if not quiet:
                extra = f" anomaly={body['anomaly']}" if body.get("anomaly") else ""
                self.log(f"{slot_id} {cm} cm -> {body.get('currentStatus')} LED {color}{extra}")
        elif not quiet or code >= 400:
            self.log(f"{slot_id} gagal: {error_text(code, body)}")
        return code, body

    def set_state(self, slot_id: str, state: str, cm: float | None = None):
        """Perintah manual: 'occupied' (motor parkir) atau 'free' (motor keluar)."""
        slot_id = slot_id.strip().upper()
        cm = distance_for(state) if cm is None else cm
        code, body = self.report(slot_id, cm)
        if code == 200:
            with self.lock:
                self.readings[slot_id] = cm
                self.heartbeat_slots.add(slot_id)
        return code, body

    def glitch(self, slot_id: str, cm: float = config.GLITCH_CM):
        """Sensor rusak: kirim nilai di luar 2..400 cm (bawaan 500 cm).

        Bacaan rusak tetap ikut heartbeat, seperti sensor yang macet sungguhan.
        """
        slot_id = slot_id.strip().upper()
        code, body = self.report(slot_id, cm)
        if code == 200:
            with self.lock:
                self.readings[slot_id] = cm
                self.heartbeat_slots.add(slot_id)
        return code, body

    def stop(self, slot_id: str) -> bool:
        """Sensor berhenti melapor: keluarkan dari heartbeat -> STALE setelah 60 dtk."""
        slot_id = slot_id.strip().upper()
        with self.lock:
            was_alive = slot_id in self.heartbeat_slots
            self.heartbeat_slots.discard(slot_id)
        self.log(f"{slot_id} berhenti melapor; backend menandai UNKNOWN setelah "
                 f"> {config.STALE_SECONDS} dtk")
        return was_alive

    def resume(self, slot_id: str):
        """Sensor hidup lagi: kirim bacaan terakhir dan masuk heartbeat lagi."""
        slot_id = slot_id.strip().upper()
        with self.lock:
            cm = self.readings.get(slot_id)
        if cm is None:
            cm = distance_for("free")
        state = "occupied" if status_from_distance(cm) == "OCCUPIED" else "free"
        return self.set_state(slot_id, state, cm)

    def adopt_from_backend(self) -> int:
        """Ambil alih semua slot berstatus AVAILABLE/OCCUPIED dari GET /slots.

        Dipakai setelah `scenario` agar slot hasil skenario ikut di-heartbeat
        seperti gateway sungguhan yang melaporkan semua sensornya. Slot UNKNOWN
        dibiarkan (sensornya dianggap bermasalah).
        """
        code, body = self.api.get_slots()
        if code != 200:
            self.log(f"adopt gagal: {error_text(code, body)}")
            return 0
        adopted = 0
        for s in body.get("slots", []):
            if s.get("status") not in ("AVAILABLE", "OCCUPIED"):
                continue
            state = "occupied" if s["status"] == "OCCUPIED" else "free"
            cm = distance_for(state)
            rcode, _ = self.report(s["slotId"], cm, quiet=True)
            if rcode == 200:
                with self.lock:
                    self.readings[s["slotId"]] = cm
                    self.heartbeat_slots.add(s["slotId"])
                adopted += 1
        self.log(f"Mengambil alih {adopted} slot (ikut heartbeat)")
        return adopted

    # --- heartbeat ------------------------------------------------------------
    def heartbeat_once(self) -> int:
        """Kirim ulang bacaan terakhir untuk semua slot yang masih hidup."""
        with self.lock:
            targets = [(s, self.readings[s]) for s in sorted(self.heartbeat_slots)]
        sent = 0
        for slot_id, cm in targets:
            try:
                code, _ = self.report(slot_id, cm, quiet=True)
                sent += code == 200
            except ApiUnavailable as exc:
                self.log(f"heartbeat: {exc}")
                break
        self.heartbeat_count += 1
        return sent

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            self.heartbeat_once()

    def start_heartbeat(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._heartbeat_loop, name="heartbeat", daemon=True)
        self._thread.start()

    def stop_heartbeat(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def occupied_slots(self) -> list[str]:
        with self.lock:
            return [s for s, cm in self.readings.items()
                    if s in self.heartbeat_slots and status_from_distance(cm) == "OCCUPIED"
                    and config.VALID_MIN_CM <= cm <= config.VALID_MAX_CM]


# ---------------------------------------------------------------------------
# Mode auto: motor datang/pergi mengikuti pola jam puncak
# ---------------------------------------------------------------------------
# Kedatangan motor per jam simulasi (untuk 40 slot). Puncak 06.30-09.00.
ARRIVALS_PER_HOUR = {6: 18, 7: 36, 8: 24, 9: 10, 10: 6, 11: 4, 12: 8, 13: 8,
                     14: 5, 15: 4, 16: 3, 17: 2}
# Peluang tiap motor yang parkir pergi dalam satu jam simulasi.
DEPART_FRACTION_PER_HOUR = {6: 0.0, 7: 0.02, 8: 0.03, 9: 0.05, 10: 0.08, 11: 0.12,
                            12: 0.25, 13: 0.2, 14: 0.25, 15: 0.3, 16: 0.4, 17: 0.5}


def sample_count(expected: float) -> int:
    """Jumlah kejadian acak dengan rata-rata `expected` (cukup untuk simulasi)."""
    whole = int(expected)
    return whole + (1 if random.random() < expected - whole else 0)


class AutoTraffic:
    """Menggerakkan jam simulasi dan membuat motor datang/pergi.

    speed = detik simulasi per 1 detik nyata (60 -> 1 detik nyata = 1 menit).
    Dengan `tap=True`, tiap motor tap kartu di gerbang dulu lalu parkir di
    slot rekomendasi (kuning). Tanpa tap, motor memilih slot AVAILABLE di
    lantai terbuka, lantai 1 lebih dulu.
    """

    def __init__(self, sim: SensorSimulator, speed: float = 60, start_hour: float = 6,
                 tap: bool = False):
        self.sim = sim
        self.speed = speed
        self.sim_seconds = start_hour * 3600
        self.tap = tap
        self.arrived = 0
        self.departed = 0
        self.turned_away = 0

    @property
    def hour(self) -> int:
        return int(self.sim_seconds // 3600) % 24

    def clock(self) -> str:
        total = int(self.sim_seconds) % 86400
        return f"{total // 3600:02d}:{(total % 3600) // 60:02d}"

    def _pick_slot(self) -> str | None:
        """Slot tujuan motor: rekomendasi gerbang (tap) atau pilihan sendiri."""
        if self.tap:
            code, body = self.sim.api.entry_tap()
            rec = body.get("recommendation") if code == 200 else None
            if rec:
                self.sim.log(f"Tap kartu -> rekomendasi {rec['slotId']} (lantai {rec['floorNumber']})")
                return rec["slotId"]
            if code == 200:
                self.sim.log("Tap kartu -> tidak ada slot (penuh), palang tetap terbuka")
                return None
            self.sim.log(f"Tap kartu -> {error_text(code, body)}; motor mencari sendiri")
        code, body = self.sim.api.get_slots()
        fcode, fbody = self.sim.api.get_floors()
        if code != 200 or fcode != 200:
            return None
        open_floors = {f["floorNumber"] for f in fbody.get("floors", []) if f.get("isOpen")}
        free = [s for s in body.get("slots", [])
                if s["status"] == "AVAILABLE" and s["floorNumber"] in open_floors]
        if not free:
            return None
        lowest_floor = min(s["floorNumber"] for s in free)  # pengemudi isi lantai bawah dulu
        return random.choice([s["slotId"] for s in free if s["floorNumber"] == lowest_floor])

    def arrive(self) -> None:
        slot = self._pick_slot()
        if slot is None:
            self.turned_away += 1
            self.sim.log("Motor datang tapi tidak menemukan slot")
            return
        code, _ = self.sim.set_state(slot, "occupied")
        if code == 200:
            self.arrived += 1

    def depart(self, slot_id: str) -> None:
        code, _ = self.sim.set_state(slot_id, "free")
        if code == 200:
            self.departed += 1

    def step(self, real_dt: float) -> None:
        """Majukan jam simulasi sebesar real_dt detik nyata x speed."""
        sim_dt = real_dt * self.speed
        hour = self.hour
        for _ in range(sample_count(ARRIVALS_PER_HOUR.get(hour, 1) * sim_dt / 3600)):
            self.arrive()
        leave_p = DEPART_FRACTION_PER_HOUR.get(hour, 0.6) * sim_dt / 3600
        for slot in self.sim.occupied_slots():
            if random.random() < leave_p:
                self.depart(slot)
        self.sim_seconds += sim_dt


# ---------------------------------------------------------------------------
# Mode manual: konsol interaktif
# ---------------------------------------------------------------------------
class ManualShell(cmd.Cmd):
    intro = ("Simulator gateway ParkSense (mode manual). Ketik 'help' untuk daftar perintah.\n"
             "Contoh: set F2-A17 occupied | set F2-A17 free | stop F2-A17 | glitch F2-A17 | scenario peak_hour")
    prompt = "parksense-sim> "

    def __init__(self, sim: SensorSimulator):
        super().__init__()
        self.sim = sim

    def _show(self) -> None:
        self.sim.panel.sync_from_backend(self.sim.api)
        print(self.sim.panel.render())

    def _guard(self, fn, *args) -> None:
        try:
            fn(*args)
        except ValueError as exc:
            print(f"Input salah: {exc}")
        except ApiUnavailable as exc:
            print(exc)

    def do_set(self, arg):
        """set <slot> occupied|free [cm]  - motor parkir / keluar (jarak wajar acak bila cm kosong)"""
        parts = arg.split()
        if len(parts) not in (2, 3) or parts[1].lower() not in ("occupied", "free"):
            print("Pemakaian: set F2-A17 occupied|free [cm]")
            return
        try:
            cm = float(parts[2]) if len(parts) == 3 else None
        except ValueError:
            print("Jarak harus angka, contoh: set F2-A17 occupied 15")
            return
        self._guard(self.sim.set_state, parts[0], parts[1].lower(), cm)
        self._show()

    def do_glitch(self, arg):
        """glitch <slot> [cm]  - sensor rusak, kirim nilai di luar rentang (bawaan 500 cm)"""
        parts = arg.split()
        if not parts:
            print("Pemakaian: glitch F2-A17 [cm]")
            return
        try:
            cm = float(parts[1]) if len(parts) > 1 else config.GLITCH_CM
        except ValueError:
            print("Jarak harus angka, contoh: glitch F2-A17 500")
            return
        self._guard(self.sim.glitch, parts[0], cm)
        self._show()

    def do_stop(self, arg):
        """stop <slot>  - sensor berhenti melapor (heartbeat dimatikan) -> STALE"""
        if not arg.strip():
            print("Pemakaian: stop F2-A17")
            return
        self._guard(self.sim.stop, arg.strip())

    def do_resume(self, arg):
        """resume <slot>  - sensor melapor lagi"""
        if not arg.strip():
            print("Pemakaian: resume F2-A17")
            return
        self._guard(self.sim.resume, arg.strip())
        self._show()

    def do_scenario(self, arg):
        """scenario reset|peak_hour|all_full|sensor_stale  - muat kondisi awal di backend lalu ambil alih slot"""
        name = arg.strip()
        if name not in SCENARIOS:
            print(f"Skenario: {', '.join(SCENARIOS)}")
            return
        try:
            code, body = self.sim.api.load_scenario(name)
            print(f"Skenario {name}: HTTP {code}" if code == 200 else error_text(code, body))
            if code == 200:
                with self.sim.lock:
                    self.sim.readings.clear()
                    self.sim.heartbeat_slots.clear()
                if name != "reset":
                    self.sim.adopt_from_backend()
        except ApiUnavailable as exc:
            print(exc)
        self._show()

    def do_adopt(self, arg):
        """adopt  - ambil alih semua slot AVAILABLE/OCCUPIED agar ikut heartbeat"""
        self._guard(self.sim.adopt_from_backend)

    def do_panel(self, arg):
        """panel  - tampilkan panel LED terkini dari GET /slots"""
        self._show()

    def do_floors(self, arg):
        """floors  - ringkasan GET /occupancy/floors"""
        try:
            code, body = self.sim.api.get_floors()
        except ApiUnavailable as exc:
            print(exc)
            return
        if code != 200:
            print(error_text(code, body))
            return
        for f in body.get("floors", []):
            print(f"Lantai {f['floorNumber']} ({'buka' if f['isOpen'] else 'tutup'}): "
                  f"available={f['available']} occupied={f['occupied']} unknown={f['unknown']} total={f['total']}")

    def do_heartbeat(self, arg):
        """heartbeat  - daftar slot yang masih dikirim ulang tiap interval"""
        with self.sim.lock:
            alive = sorted(self.sim.heartbeat_slots)
        print(f"Interval {self.sim.heartbeat_seconds:g} dtk, {len(alive)} slot: {', '.join(alive) or '-'}")

    def do_quit(self, arg):
        """quit  - keluar"""
        return True

    do_exit = do_quit
    do_EOF = do_quit

    def emptyline(self):
        pass


# ---------------------------------------------------------------------------
# Titik masuk CLI
# ---------------------------------------------------------------------------
def run_auto(sim: SensorSimulator, args) -> None:
    if args.seed is not None:
        random.seed(args.seed)
    traffic = AutoTraffic(sim, speed=args.speed, start_hour=args.start_hour, tap=args.tap)
    if not args.no_adopt:
        sim.adopt_from_backend()
    sim.start_heartbeat()
    started = time.monotonic()
    tick = 0.5
    last_render = 0.0
    try:
        while traffic.sim_seconds < args.end_hour * 3600:
            if args.duration and time.monotonic() - started >= args.duration:
                break
            traffic.step(tick)
            if time.monotonic() - last_render >= 1:
                sim.panel.sync_from_backend(sim.api)
                screen = [f"ParkSense simulator AUTO  jam simulasi {traffic.clock()}  (speed x{args.speed:g})",
                          f"datang={traffic.arrived} pergi={traffic.departed} tak dapat slot={traffic.turned_away}",
                          sim.panel.render(), "Kejadian terakhir:"] + list(sim.events)[-8:]
                if not args.no_clear:
                    print("\033[H\033[2J", end="")
                print("\n".join(screen), flush=True)
                last_render = time.monotonic()
            time.sleep(tick)
    except KeyboardInterrupt:
        print("\nDihentikan.")
    finally:
        sim.stop_heartbeat()
    print(f"Selesai di jam simulasi {traffic.clock()}: datang={traffic.arrived}, pergi={traffic.departed}, "
          f"tak dapat slot={traffic.turned_away}")


def run_fault(sim: SensorSimulator, args) -> int:
    if args.kind == "glitch":
        code, body = sim.glitch(args.slot, args.cm)
        print(sim.panel.render())
        return 0 if code == 200 else 1
    # kind == "stop": nyalakan sensor, jaga slot --keep tetap hidup, biarkan slot target basi
    wait = args.wait if args.wait is not None else config.STALE_SECONDS + 5
    sim.set_state(args.slot, "occupied")
    for keep in args.keep:
        sim.set_state(keep, "occupied")
    sim.stop(args.slot)
    sim.start_heartbeat()
    print(f"Menunggu {wait:g} dtk (heartbeat tetap berjalan untuk: {', '.join(args.keep) or '-'})...")
    try:
        time.sleep(wait)
    finally:
        sim.stop_heartbeat()
    code, body = sim.api.get_slots()
    for s in body.get("slots", []):
        if s["slotId"] in [args.slot.upper()] + [k.upper() for k in args.keep]:
            print(f"{s['slotId']}: status={s['status']} ledColor={s['ledColor']} lastUpdate={s['lastUpdate']}")
    sim.panel.sync_from_backend(sim.api)
    print(sim.panel.render())
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--url", default=config.BASE_URL, help="base URL API (bawaan %(default)s)")
    common.add_argument("--key", default=config.DEVICE_KEY, help="X-Device-Key")
    common.add_argument("--no-color", action="store_true", help="panel tanpa warna ANSI")
    common.add_argument("--heartbeat", type=float, default=config.HEARTBEAT_SECONDS,
                        help="interval heartbeat dtk (harus <= 30; bawaan %(default)s)")

    parser = argparse.ArgumentParser(prog="python -m simulator.sensor_sim", parents=[common],
                                     description="Simulator gateway IoT ParkSense")
    sub = parser.add_subparsers(dest="mode")

    m = sub.add_parser("manual", parents=[common], help="konsol interaktif")
    m.add_argument("--adopt", action="store_true", help="ambil alih semua slot saat mulai")

    a = sub.add_parser("auto", parents=[common], help="lalu lintas motor otomatis")
    a.add_argument("--speed", type=float, default=60, help="detik simulasi per detik nyata (bawaan 60)")
    a.add_argument("--start-hour", type=float, default=6, help="jam mulai simulasi (bawaan 6)")
    a.add_argument("--end-hour", type=float, default=18, help="jam selesai simulasi (bawaan 18)")
    a.add_argument("--duration", type=float, default=0, help="batas waktu nyata dalam detik (0 = tanpa batas)")
    a.add_argument("--tap", action="store_true", help="motor tap kartu di gerbang dan ikut rekomendasi")
    a.add_argument("--no-adopt", action="store_true", help="jangan ambil alih slot yang sudah ada")
    a.add_argument("--no-clear", action="store_true", help="jangan bersihkan layar tiap refresh")
    a.add_argument("--seed", type=int, help="seed acak agar dapat diulang")

    f = sub.add_parser("fault", parents=[common], help="sensor bermasalah")
    fsub = f.add_subparsers(dest="kind", required=True)
    g = fsub.add_parser("glitch", parents=[common], help="kirim nilai rusak (bawaan 500 cm)")
    g.add_argument("slot")
    g.add_argument("--cm", type=float, default=config.GLITCH_CM)
    st = fsub.add_parser("stop", parents=[common], help="sensor berhenti melapor -> STALE")
    st.add_argument("slot")
    st.add_argument("--keep", nargs="*", default=[], help="slot pembanding yang tetap di-heartbeat")
    st.add_argument("--wait", type=float, help="lama menunggu dtk (bawaan STALE_SECONDS + 5)")

    s = sub.add_parser("set", parents=[common], help="satu laporan sekali jalan")
    s.add_argument("slot")
    s.add_argument("state", choices=["occupied", "free"])
    s.add_argument("--cm", type=float)

    sc = sub.add_parser("scenario", parents=[common], help="POST /dev/scenario/{name}")
    sc.add_argument("name", choices=SCENARIOS)

    sub.add_parser("panel", parents=[common], help="tampilkan panel LED dari GET /slots")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    enable_windows_ansi()
    if args.heartbeat > 30:
        print("Peringatan: heartbeat > 30 dtk berisiko slot ditandai STALE oleh backend.")
    api = ApiClient(args.url, args.key)
    panel = LedPanel(use_color=not args.no_color)
    mode = args.mode or "manual"
    sim = SensorSimulator(api, panel, heartbeat_seconds=args.heartbeat,
                          on_event=None if mode == "auto" else print)
    try:
        if mode == "manual":
            if getattr(args, "adopt", False):
                sim.adopt_from_backend()
            sim.start_heartbeat()
            try:
                ManualShell(sim).cmdloop()
            finally:
                sim.stop_heartbeat()
        elif mode == "auto":
            run_auto(sim, args)
        elif mode == "fault":
            return run_fault(sim, args)
        elif mode == "set":
            code, _ = sim.set_state(args.slot, args.state, args.cm)
            print(panel.render())
            return 0 if code == 200 else 1
        elif mode == "scenario":
            code, body = api.load_scenario(args.name)
            print(f"Skenario {args.name}: HTTP {code} {body}")
            return 0 if code == 200 else 1
        elif mode == "panel":
            ok = panel.sync_from_backend(api)
            print(panel.render())
            return 0 if ok else 1
    except ApiUnavailable as exc:
        print(exc)
        return 2
    except ValueError as exc:
        print(f"Input salah: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
