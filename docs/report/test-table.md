# Tabel Pengujian Prototipe ParkSense (Deliverable 3)

Pengujian dijalankan pada 25-11-2026 terhadap backend yang berjalan lokal (`http://127.0.0.1:8000`).
Semua bukti disimpan di `tests/evidence/`. Log `run_all_*.log` dihasilkan oleh `python tests/run_all.py`
dan memuat respons HTTP asli untuk TC-01 sampai TC-09.

| ID | Skenario | Langkah / Input | Hasil Diharapkan | Hasil Aktual | Status | Bukti |
|---|---|---|---|---|---|---|
| TC-01 | Tap kartu valid pada jam puncak | 1. `POST /dev/scenario/peak_hour` 2. `POST /gate/entry-tap` dengan `cardId: RFID-04A1B7C2` | 200; rekomendasi lantai 2 (slot AVAILABLE); `displayMessage` "Lantai 2 - Slot ..."; `gateAction: OPEN_BARRIER`; LED slot rekomendasi YELLOW | 200; rekomendasi lantai 2; `OPEN_BARRIER`; LED slot rekomendasi YELLOW di `GET /slots` dan di peta slot halaman gerbang | Lulus | `run_all_20261126-182951.log`; `tc-01-yellow-led.png` |
| TC-02 | Semua lantai yang dibuka penuh | 1. `POST /dev/scenario/all_full` 2. `POST /gate/entry-tap` kartu valid | 200; `recommendation: null`; display menampilkan info penuh; palang tetap terbuka (`OPEN_BARRIER`) | 200; `recommendation: null`; display "Parkir penuh. Lantai 1: 0 tersedia \| Lantai 2: 0 tersedia"; `OPEN_BARRIER` | Lulus | `run_all_20261126-182951.log`; `tc-02-all-full-gate.png` |
| TC-03 | Kartu tidak valid | `POST /gate/entry-tap` dengan kartu tidak terdaftar (API: `RFID-TIDAK-ADA`; halaman gerbang: preset `RFID-00000000`) | 400 `INVALID_CARD`; palang tidak terbuka; display menampilkan penolakan | 400 `INVALID_CARD` "Kartu tidak terdaftar; palang tidak dibuka"; respons tanpa `gateAction`; halaman gerbang menampilkan "Kartu ditolak" dan "AKSES DITOLAK" | Lulus | `run_all_20261126-182951.log`; `tc-03-invalid-card.png`; `tc-03-invalid-card-gate.png` |
| TC-04 | Motor parkir lalu keluar | 1. `PUT /slots/F1-A05/status` status `OCCUPIED` (18.4 cm) 2. `GET /occupancy/floors` 3. PUT status `AVAILABLE` (150 cm) 4. `GET /occupancy/floors` | LED RED lalu GREEN; `available` lantai 1 berkurang 1 lalu kembali | LED RED lalu GREEN; `available` lantai 1 berkurang 1 lalu kembali ke nilai awal (dijalankan oleh `run_all.py` dan runner simulator) | Lulus | `run_all_20261126-182951.log`; `TC-04_20261125-133615.log`; `tc-04-simulator-led-panel.png` |
| TC-05 | Sensor bermasalah | a) `PUT /slots/F1-A03/status` dengan `rawSensorValue: 500` b) `POST /dev/scenario/sensor_stale` (F1-A05 dan F1-A06 basi), lalu tap kartu valid. Varian sensor benar-benar berhenti melapor (> 60 detik) dibuktikan oleh runner simulator | Slot UNKNOWN, LED OFF, tidak direkomendasikan, dihitung di `unknown` pada `GET /occupancy/floors`, peringatan muncul di dashboard | a) F1-A03 UNKNOWN, LED OFF, `unknown` lantai 1 bertambah 1 b) F1-A05 dan F1-A06 UNKNOWN, LED OFF, tidak direkomendasikan. Runner simulator: 29/29 cek lulus untuk varian glitch, scenario, dan stale. Dashboard menampilkan peringatan sensor | Lulus | `run_all_20261126-182951.log`; `TC-05_20261125-133622.log`; `TC-05_20261125-133628.log`; `TC-05_20261125-133638.log`; `dashboard/tc05_dashboard_unknown.png` |
| TC-06 | Prediksi okupansi jam puncak | 1. `GET /ai/predictions/occupancy?fromHour=6&toHour=9` 2. Ulangi dengan `fromHour=9&toHour=6` | 1) 200: prediksi jam 6, 7, 8, 9 per lantai + `advisory` 2) 400 `INVALID_TIME_WINDOW` | 1) 200: prediksi jam 6-9 untuk lantai 1 dan 2 + advisory dalam bahasa Indonesia 2) 400 `INVALID_TIME_WINDOW`; dashboard menampilkan pesan galat | Lulus | `run_all_20261126-182951.log`; `tc-06-invalid-time-window.png`; `dashboard/tc06_prediction_chart.png`; `dashboard/tc06_invalid_window.png` |
| TC-07 | Otorisasi | Panggil endpoint tanpa header kunci / dengan kunci salah | 401 `UNAUTHORIZED` (termasuk endpoint prediksi yang dipanggil dengan X-Device-Key, karena hanya menerima Bearer) | 401 untuk tap tanpa kunci, PUT dengan kunci salah, dan prediksi dengan X-Device-Key | Lulus | `run_all_20261126-182951.log`; `tc-07-unauthorized-no-key.png`; `tc-07-unauthorized-wrong-credential.png` |
| TC-08 | Status tidak valid | `PUT /slots/F1-A01/status` dengan `status: "BROKEN"` | 400 `INVALID_STATUS` | 400 `INVALID_STATUS` | Lulus | `run_all_20261126-182951.log`; `tc-08-invalid-status.png` |
| TC-09 | Modul rekomendasi gagal | 1. `POST /dev/fault/recommendation?enabled=true` 2. Tap kartu valid 3. Pulihkan `enabled=false` | 500 `RECOMMENDATION_FAILED`; `gateAction: OPEN_BARRIER` tetap; display menampilkan ketersediaan per lantai (`floors`) | 500 `RECOMMENDATION_FAILED` dengan `OPEN_BARRIER` dan `floors` 2 lantai; halaman gerbang menampilkan "Silakan masuk. Lantai 1: 1 tersedia \| Lantai 2: 16 tersedia"; setelah dipulihkan tap kembali 200 | Lulus | `run_all_20261126-182951.log`; `tc-09-recommendation-failed.png`; `tc-09-recommendation-failed-gate.png` |

## Sumber bukti per TC

| TC | Bukti API (respons/log) | Bukti tampilan |
|---|---|---|
| TC-01 | `run_all_20261126-182951.log` | Halaman gerbang: `tc-01-yellow-led.png` |
| TC-02 | `run_all_20261126-182951.log` | Halaman gerbang: `tc-02-all-full-gate.png` |
| TC-03 | `run_all_20261126-182951.log`; `tc-03-invalid-card.png` | Halaman gerbang: `tc-03-invalid-card-gate.png` |
| TC-04 | `run_all_20261126-182951.log`; `TC-04_20261125-133615.log` (runner simulator) | Panel LED simulator: `tc-04-simulator-led-panel.png` |
| TC-05 | `run_all_20261126-182951.log`; `TC-05_20261125-133622.log`; `TC-05_20261125-133628.log`; `TC-05_20261125-133638.log` (runner simulator) | Dashboard: `dashboard/tc05_dashboard_unknown.png` |
| TC-06 | `run_all_20261126-182951.log`; `tc-06-invalid-time-window.png` | Dashboard: `dashboard/tc06_prediction_chart.png`, `dashboard/tc06_invalid_window.png` |
| TC-07 | `run_all_20261126-182951.log`; `tc-07-unauthorized-no-key.png`; `tc-07-unauthorized-wrong-credential.png` | – |
| TC-08 | `run_all_20261126-182951.log`; `tc-08-invalid-status.png` | – |
| TC-09 | `run_all_20261126-182951.log`; `tc-09-recommendation-failed.png` | Halaman gerbang: `tc-09-recommendation-failed-gate.png` |