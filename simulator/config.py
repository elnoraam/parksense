"""Konfigurasi bersama simulator IoT ParkSense.

Semua alamat dan kunci dibaca dari SATU tempat ini. Nilai bawaan mengikuti
kontrak AGENTS.md Bagian 4; nilai resminya didefinisikan di `backend/auth.py`.
Bisa ditimpa lewat variabel lingkungan tanpa mengubah kode.
"""
import os

# Alamat dasar REST API backend (kontrak: http://localhost:8000/api/v1)
BASE_URL = os.environ.get("PARKSENSE_URL", "http://localhost:8000/api/v1").rstrip("/")

# Kunci perangkat untuk header X-Device-Key (gateway IoT = perangkat)
DEVICE_KEY = os.environ.get("PARKSENSE_DEVICE_KEY", "parksense-dev-key")

# Kartu RFID valid contoh (dipakai opsi --tap di mode auto dan runner TC-05)
VALID_CARD = os.environ.get("PARKSENSE_VALID_CARD", "RFID-04A1B7C2")

# Aturan sensor dari kontrak
OCCUPIED_THRESHOLD_CM = 30      # jarak < 30 cm = OCCUPIED
VALID_MIN_CM = 2                # rentang valid 2..400 cm
VALID_MAX_CM = 400
GLITCH_CM = 500                 # nilai rusak untuk mode fault (di luar rentang)

# Backend menandai slot UNKNOWN bila tidak ada laporan > STALE_SECONDS.
# Ikuti nilai backend: bila backend dijalankan dengan STALE_SECONDS=600, set juga di sini.
STALE_SECONDS = int(os.environ.get("STALE_SECONDS", "60"))

# Heartbeat harus <= 30 detik agar slot tidak pernah basi selama sensor "hidup".
HEARTBEAT_SECONDS = float(os.environ.get("HEARTBEAT_SECONDS", "20"))

# Batas waktu satu permintaan HTTP (detik)
HTTP_TIMEOUT = float(os.environ.get("PARKSENSE_HTTP_TIMEOUT", "5"))

# Tata letak gedung (kontrak: 2 lantai x 20 slot)
FLOORS = (1, 2)
SLOTS_PER_FLOOR = 20
