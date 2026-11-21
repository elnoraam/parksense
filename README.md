# ParkSense — Prototipe Deliverable 3 (II3120, Kelompok 05)

Layanan parkir cerdas IoT + AI untuk gedung parkir motor ITB Jatinangor. Seluruh prototipe berjalan virtual di laptop.

## Menjalankan backend
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```
- Dokumentasi interaktif (Swagger): http://localhost:8000/docs
- Status dan modul AI yang dipakai: http://localhost:8000/health
- Halaman web statis: http://localhost:8000/web/gate/ dan http://localhost:8000/web/dashboard/

Konfigurasi opsional (variabel lingkungan): `PARKSENSE_DB` (default `parksense.db`), `PARKSENSE_DEVICE_KEY`, `PARKSENSE_DASHBOARD_TOKEN`, `STALE_SECONDS` (default 60), `RECOMMEND_TTL_SECONDS` (default 120).

## Mencoba dengan curl
```bash
KEY="X-Device-Key: parksense-dev-key"; TOKEN="Authorization: Bearer dev-dashboard-token"
B=http://localhost:8000/api/v1

curl -X POST $B/dev/scenario/peak_hour -H "$KEY"                 # lantai 1 hampir penuh
curl -X POST $B/gate/entry-tap -H "$KEY" -H "Content-Type: application/json" \
  -d '{"gateId":"GATE-IN-01","cardId":"RFID-04A1B7C2","vehicleType":"MOTORCYCLE","tapTime":"2026-11-21T07:42:15+07:00"}'
curl -X PUT $B/slots/F2-A17/status -H "$KEY" -H "Content-Type: application/json" \
  -d '{"gatewayId":"ESP32-GW-F2","sensorType":"ULTRASONIC","rawSensorValue":18.4,"unit":"cm","status":"OCCUPIED","measuredAt":"2026-11-21T07:43:02+07:00"}'
curl $B/occupancy/floors -H "$TOKEN"
curl "$B/ai/predictions/occupancy?fromHour=6&toHour=9" -H "$TOKEN"
```

## Tes
```bash
python -m pytest            # 12 tes: TC-01 s.d. TC-09 + kasus galat
python -m backend.export_openapi   # menulis docs/openapi.json
```

## Struktur
`backend/` (Ellen) · `ai/` (Salma) · `simulator/` (Lukman) · `web/gate/` (Belva) · `web/dashboard/` (Sherry) · `tests/` dan `docs/` (Indah, semua).