"""Database SQLite + data awal (seed). Satu koneksi bersama dengan lock."""
import os
import sqlite3
import threading

from .util import iso, now

lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SLOTS_PER_FLOOR = 20
FLOORS = (1, 2, 3)
OPEN_FLOORS = {1, 2}  # lantai 3 ditutup (sesuai temuan lantai atas sering ditutup)
VALID_CARDS = ("RFID-04A1B7C2", "RFID-0B22C3D4", "RFID-1F33E5A6")

SCHEMA = """
CREATE TABLE IF NOT EXISTS floors (
  floor_number INTEGER PRIMARY KEY,
  is_open INTEGER NOT NULL,
  total INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS slots (
  slot_id TEXT PRIMARY KEY,
  floor_number INTEGER NOT NULL,
  status TEXT NOT NULL,
  led_color TEXT NOT NULL,
  distance REAL NOT NULL,
  raw_value REAL,
  last_update TEXT,
  recommended_at TEXT
);
CREATE TABLE IF NOT EXISTS cards (card_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  card_id TEXT, gate_id TEXT, vehicle_type TEXT, tap_time TEXT,
  floor_number INTEGER, slot_id TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS readings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slot_id TEXT, gateway_id TEXT, sensor_type TEXT,
  raw_value REAL, unit TEXT, status TEXT, measured_at TEXT
);
"""

# Status dan flag uji yang hidup selama proses berjalan
state = {"fail_recommendation": False}


def init(path: str | None = None) -> sqlite3.Connection:
    """Buka koneksi baru (path ':memory:' untuk tes) dan isi seed bila kosong."""
    global _conn
    path = path or os.getenv("PARKSENSE_DB", "parksense.db")
    _conn = sqlite3.connect(path, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.executescript(SCHEMA)
    if _conn.execute("SELECT COUNT(*) FROM floors").fetchone()[0] == 0:
        _seed(_conn)
    state["fail_recommendation"] = False
    return _conn


def conn() -> sqlite3.Connection:
    if _conn is None:
        init()
    return _conn  # type: ignore[return-value]


def _seed(c: sqlite3.Connection) -> None:
    for fl in FLOORS:
        c.execute(
            "INSERT INTO floors VALUES (?,?,?)",
            (fl, 1 if fl in OPEN_FLOORS else 0, SLOTS_PER_FLOOR),
        )
        for n in range(1, SLOTS_PER_FLOOR + 1):
            c.execute(
                "INSERT INTO slots (slot_id, floor_number, status, led_color, distance) "
                "VALUES (?,?,?,?,?)",
                (f"F{fl}-A{n:02d}", fl, "AVAILABLE", "GREEN", (n - 1) / (SLOTS_PER_FLOOR - 1)),
            )
    for card in VALID_CARDS:
        c.execute("INSERT OR IGNORE INTO cards VALUES (?)", (card,))
    c.commit()


def reset_all() -> None:
    """Kembalikan ke kondisi awal: semua slot kosong, riwayat dibersihkan."""
    with lock:
        c = conn()
        c.execute("DELETE FROM entries")
        c.execute("DELETE FROM readings")
        c.execute(
            "UPDATE slots SET status='AVAILABLE', led_color='GREEN', raw_value=NULL, "
            "last_update=NULL, recommended_at=NULL"
        )
        for fl in FLOORS:
            c.execute("UPDATE floors SET is_open=? WHERE floor_number=?", (1 if fl in OPEN_FLOORS else 0, fl))
        c.commit()
        state["fail_recommendation"] = False


def stamp() -> str:
    return iso(now())
