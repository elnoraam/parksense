"""Alat bantu bersama untuk runner skenario: log bukti bertanda waktu + pengecekan."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from simulator import config
from simulator.sensor_sim import WIB, ApiClient

# <repo>/tests/evidence (folder bukti uji bersama)
DEFAULT_EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "tests" / "evidence"


class EvidenceLog:
    """Menulis log uji ke tests/evidence/<TC>_<tanggal-jam>.log dan mencatat hasil cek."""

    def __init__(self, test_id: str, title: str, evidence_dir: Path | str = DEFAULT_EVIDENCE_DIR,
                 echo: bool = True, base_url: str = config.BASE_URL):
        self.test_id = test_id
        self.echo = echo
        self.results: list[tuple[str, bool]] = []
        folder = Path(evidence_dir)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(WIB).strftime("%Y%m%d-%H%M%S")
        self.path = folder / f"{test_id}_{stamp}.log"
        self._fh = self.path.open("w", encoding="utf-8")
        self.write(f"=== {test_id}: {title} ===")
        self.write(f"Base URL : {base_url}")

    def write(self, message: str) -> None:
        line = f"[{datetime.now(WIB).isoformat(timespec='seconds')}] {message}"
        self._fh.write(line + "\n")
        self._fh.flush()
        if self.echo:
            print(line)

    def step(self, message: str) -> None:
        self.write(f"LANGKAH  {message}")

    def http(self, label: str, code: int, body) -> None:
        """Simpan respons HTTP mentah sebagai bukti."""
        self.write(f"HTTP     {label} -> {code} {json.dumps(body, ensure_ascii=False)}")

    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        ok = bool(condition)
        self.results.append((name, ok))
        self.write(f"{'LULUS' if ok else 'GAGAL'}    {name}" + (f" ({detail})" if detail else ""))
        return ok

    def finish(self) -> int:
        """Tulis ringkasan. Kode keluar 0 bila semua cek lulus."""
        passed = sum(ok for _, ok in self.results)
        all_ok = passed == len(self.results) and self.results
        self.write(f"HASIL    {self.test_id}: {'LULUS' if all_ok else 'GAGAL'} ({passed}/{len(self.results)} cek)")
        self.write(f"Log bukti: {self.path}")
        self._fh.close()
        return 0 if all_ok else 1


def base_parser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--url", default=config.BASE_URL, help="base URL API (bawaan %(default)s)")
    p.add_argument("--key", default=config.DEVICE_KEY, help="X-Device-Key")
    p.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE_DIR), help="folder log bukti")
    return p


def find_slot(slots_body: dict, slot_id: str) -> dict:
    return next((s for s in slots_body.get("slots", []) if s["slotId"] == slot_id), {})


def find_floor(floors_body: dict, floor: int) -> dict:
    return next((f for f in floors_body.get("floors", []) if f["floorNumber"] == floor), {})


def load_scenario(api: ApiClient, log: EvidenceLog, name: str) -> bool:
    log.step(f"POST /dev/scenario/{name}")
    code, body = api.load_scenario(name)
    log.http(f"POST /dev/scenario/{name}", code, body)
    return log.check(f"scenario {name} dimuat (200)", code == 200, f"HTTP {code}")
