"""Backend tiruan (test double) untuk menguji simulator tanpa backend asli.

HANYA untuk uji paket `simulator/`. Bukan pengganti `backend/`: logikanya
sengaja minimal dan mengikuti bentuk respons FINAL di AGENTS.md Bagian 4
(endpoint yang dipakai simulator dan runner skenario saja).

Menjalankan manual:  python -m simulator.tests.mock_backend --port 8000
"""
from __future__ import annotations

import argparse
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

WIB = timezone(timedelta(hours=7))
DEVICE_KEY = "parksense-dev-key"
DASHBOARD_TOKEN = "dev-dashboard-token"
VALID_CARDS = {"RFID-04A1B7C2"}
STATUSES = {"AVAILABLE", "OCCUPIED", "UNKNOWN"}
LED = {"AVAILABLE": "GREEN", "OCCUPIED": "RED", "UNKNOWN": "OFF"}


class MockState:
    def __init__(self, stale_seconds: float = 60, recommend_ttl: float = 120):
        self.stale_seconds = stale_seconds
        self.recommend_ttl = recommend_ttl
        self.lock = threading.Lock()
        self.put_log: list[dict] = []  # semua payload PUT yang diterima (untuk tes)
        self.reset()

    def reset(self):
        self.floor_open = {1: True, 2: False}
        self.slots = {f"F{f}-A{n:02d}": {"floorNumber": f, "status": "AVAILABLE", "lastUpdate": None,
                                          "recommendedUntil": None}
                      for f in (1, 2) for n in range(1, 21)}
        self.fault = False

    def now(self):
        return datetime.now(WIB)

    def effective(self, slot_id):
        """Status dan warna LED saat dibaca (termasuk aturan basi dan kuning)."""
        s = self.slots[slot_id]
        status = s["status"]
        if s["lastUpdate"] and (self.now() - s["lastUpdate"]).total_seconds() > self.stale_seconds:
            status = "UNKNOWN"
        color = LED[status]
        if status == "AVAILABLE" and s["recommendedUntil"] and s["recommendedUntil"] > self.now():
            color = "YELLOW"
        return status, color

    def floors(self):
        out = []
        for f in (1, 2):
            ids = [i for i, s in self.slots.items() if s["floorNumber"] == f]
            st = [self.effective(i)[0] for i in ids]
            out.append({"floorNumber": f, "isOpen": self.floor_open[f], "total": len(ids),
                        "available": st.count("AVAILABLE"), "occupied": st.count("OCCUPIED"),
                        "unknown": st.count("UNKNOWN")})
        return out


def make_handler(state: MockState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # senyap saat tes
            pass

        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _err(self, code, err, msg):
            self._send(code, {"status": code, "code": err, "message": msg})

        def _auth(self, allow_bearer):
            if self.headers.get("X-Device-Key") == DEVICE_KEY:
                return True
            if allow_bearer and self.headers.get("Authorization") == f"Bearer {DASHBOARD_TOKEN}":
                return True
            self._err(401, "UNAUTHORIZED", "Kunci tidak valid")
            return False

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return None

        def _path(self):
            path = urlparse(self.path).path
            return path[len("/api/v1"):] if path.startswith("/api/v1") else None

        def do_GET(self):
            path = self._path()
            if path not in ("/slots", "/occupancy/floors"):
                return self._err(404, "NOT_FOUND", "Path tidak ada")
            if not self._auth(True):
                return
            with state.lock:
                gen = state.now().isoformat(timespec="seconds")
                if path == "/slots":
                    slots = []
                    for i, s in state.slots.items():
                        st, color = state.effective(i)
                        lu = s["lastUpdate"].isoformat(timespec="seconds") if s["lastUpdate"] else None
                        slots.append({"slotId": i, "floorNumber": s["floorNumber"], "status": st,
                                      "ledColor": color, "lastUpdate": lu})
                    return self._send(200, {"slots": slots, "generatedAt": gen})
                return self._send(200, {"floors": state.floors(), "generatedAt": gen})

        def do_PUT(self):
            path = self._path() or ""
            m = re.match(r"^/slots/([^/]+)/status$", path)
            if not m:
                return self._err(404, "NOT_FOUND", "Path tidak ada")
            if not self._auth(False):
                return
            body = self._body()
            need = {"gatewayId": str, "sensorType": str, "rawSensorValue": (int, float), "unit": str,
                    "status": str, "measuredAt": str}
            if not isinstance(body, dict) or any(not isinstance(body.get(k), t) for k, t in need.items()):
                return self._err(400, "INVALID_REQUEST", "Payload tidak lengkap")
            if body["status"] not in STATUSES:
                return self._err(400, "INVALID_STATUS", "Status tidak valid")
            slot_id = m.group(1)
            with state.lock:
                if slot_id not in state.slots:
                    return self._err(404, "SLOT_NOT_FOUND", "Slot tidak dikenal")
                state.put_log.append({"slotId": slot_id, **body})
                s = state.slots[slot_id]
                resp = {}
                if not 2 <= body["rawSensorValue"] <= 400:
                    s["status"] = "UNKNOWN"
                    resp["anomaly"] = "OUT_OF_RANGE"
                else:
                    s["status"] = body["status"]
                s["lastUpdate"] = state.now()
                if s["status"] != "AVAILABLE":
                    s["recommendedUntil"] = None
                st, color = state.effective(slot_id)
                resp.update({"slotId": slot_id, "currentStatus": st, "ledCommand": {"color": color, "sent": True}})
            return self._send(200, resp)

        def do_POST(self):
            path = self._path() or ""
            if not self._auth(False):
                return
            m = re.match(r"^/dev/scenario/([a-z_]+)$", path)
            with state.lock:
                if m:
                    name = m.group(1)
                    state.reset()
                    now = state.now()
                    if name == "peak_hour":
                        state.floor_open[2] = True
                        for n in range(1, 19):
                            state.slots[f"F1-A{n:02d}"]["status"] = "OCCUPIED"
                        for s in state.slots.values():
                            s["lastUpdate"] = now
                    elif name == "all_full":
                        state.floor_open[2] = True
                        for s in state.slots.values():
                            s["status"], s["lastUpdate"] = "OCCUPIED", now
                    elif name == "sensor_stale":
                        for s in state.slots.values():
                            s["lastUpdate"] = now
                        state.slots["F1-A03"]["lastUpdate"] = now - timedelta(seconds=state.stale_seconds + 30)
                    elif name != "reset":
                        return self._err(404, "SCENARIO_NOT_FOUND", "Skenario tidak dikenal")
                    return self._send(200, {"scenario": name, "floors": state.floors()})
                if path.startswith("/dev/fault/recommendation"):
                    state.fault = "enabled=true" in self.path
                    return self._send(200, {"enabled": state.fault})
                if path == "/gate/entry-tap":
                    body = self._body() or {}
                    if body.get("cardId") not in VALID_CARDS:
                        return self._err(400, "INVALID_CARD", "Kartu tidak terdaftar")
                    if state.fault:
                        return self._send(500, {"status": 500, "code": "RECOMMENDATION_FAILED",
                                                "message": "Rekomendasi gagal", "gateAction": "OPEN_BARRIER",
                                                "displayMessage": "Silakan cari slot", "floors": state.floors()})
                    cands = [i for i, s in sorted(state.slots.items())
                             if state.floor_open[s["floorNumber"]] and state.effective(i) == ("AVAILABLE", "GREEN")]
                    if not cands:
                        return self._send(200, {"recommendation": None, "gateAction": "OPEN_BARRIER",
                                                "displayMessage": "Parkir penuh"})
                    # pilih lantai dengan sisa slot terbanyak, lalu ID terkecil
                    free = {f: sum(1 for c in cands if state.slots[c]["floorNumber"] == f) for f in (1, 2)}
                    best_floor = max(free, key=lambda f: (free[f], -f))
                    slot_id = next(c for c in cands if state.slots[c]["floorNumber"] == best_floor)
                    state.slots[slot_id]["recommendedUntil"] = state.now() + timedelta(seconds=state.recommend_ttl)
                    return self._send(200, {"recommendation": {"floorNumber": best_floor, "slotId": slot_id},
                                            "gateAction": "OPEN_BARRIER",
                                            "displayMessage": f"Lantai {best_floor}, slot {slot_id}"})
            return self._err(404, "NOT_FOUND", "Path tidak ada")

    return Handler


def start_mock(port: int = 0, stale_seconds: float = 60):
    """Jalankan backend tiruan di thread latar. Mengembalikan (server, state, base_url)."""
    state = MockState(stale_seconds=stale_seconds)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, state, f"http://127.0.0.1:{server.server_address[1]}/api/v1"


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--stale", type=float, default=60)
    a = p.parse_args()
    srv, _, url = start_mock(a.port, a.stale)
    print(f"Backend tiruan berjalan di {url} (Ctrl+C untuk berhenti)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()
