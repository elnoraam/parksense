# Keterlacakan Pengujian ParkSense

Dokumen ini memetakan setiap kasus uji (TC) ke endpoint REST, operasi SoaML, kontrak layanan, dan aktivitas BPMN To-Be. Sumber: Deliverable 2 (SoaML, BPMN To-Be, spesifikasi REST API) dan Deliverable 3 (pengujian).

## 1. Pemetaan TC ke endpoint, SoaML, dan BPMN To-Be

| TC | Skenario | Endpoint | Operasi SoaML | Kontrak layanan | Aktivitas BPMN To-Be | Bukti |
|---|---|---|---|---|---|---|
| TC-01 | Tap kartu valid pada jam puncak | `POST /gate/entry-tap` | `validateUserCard()`, `recordEntryTime()`, `requestSlotRecommendation()`, `setLedState()` | AccessService, RecommendationService, SlotRecommendationService, LedControlService | Tahap 2: "Validasi kartu & catat masuk", "AI pilih lantai & slot", "Tampilkan lantai & slot, buka palang". Tahap 3: "Nyalakan LED slot rekomendasi" | `tests/evidence/tc-01-yellow-led.png`, log `run_all` |
| TC-02 | Semua lantai penuh | `POST /gate/entry-tap`, `GET /occupancy/floors` | `requestSlotRecommendation()` (hasil `recommendationUnavailable`), `getFloorOccupancy()` | RecommendationService, OccupancyQueryService | Tahap 2: "Tampilkan lantai & slot, buka palang" (info ketersediaan per lantai) | `tc-02-all-full-gate.png`, log `run_all` |
| TC-03 | Kartu tidak valid | `POST /gate/entry-tap` | `validateUserCard()` | AccessService | Tahap 2: "Validasi kartu & catat masuk" (jalur gagal, palang tidak terbuka) | `tc-03-invalid-card.png`, `tc-03-invalid-card-gate.png` |
| TC-04 | Motor parkir lalu keluar | `PUT /slots/{slot_id}/status`, `GET /occupancy/floors` | `updateSlotStatus()`, `setLedState()`, `getFloorOccupancy()` | SlotSensingService, LedControlService, OccupancyQueryService | Tahap 4: "Deteksi kendaraan & kirim status". Tahap 5: "Deteksi motor keluar slot & kirim status kosong" | `TC-04_20261125-133615.log`, `tc-04-simulator-led-panel.png` |
| TC-05 | Sensor bermasalah (500 cm, `stop`, `sensor_stale`) | `PUT /slots/{slot_id}/status`, `GET /slots`, `GET /occupancy/floors` | `detectSensorAnomaly()`, `updateSlotStatus()`, `setLedState()`, `getFloorOccupancy()` | AnomalyPredictionService, SlotSensingService, LedControlService, OccupancyQueryService | Subproses: "Perbarui status slot, LED & AI cek anomali" (pengelola menerima peringatan) | `TC-05_20261125-133622.log`, `TC-05_20261125-133628.log`, `TC-05_20261125-133638.log`, `tc-05-simulator-glitch.png`, `dashboard/tc05_dashboard_unknown.png` |
| TC-06 | Prediksi jam puncak dan rentang jam salah | `GET /ai/predictions/occupancy` | `predictOccupancy(timeWindow)`, `getOccupancyPrediction()` | PredictionQueryService, AnomalyPredictionService | Subproses: "Perbarui status slot, LED & AI cek anomali" (AI memprediksi okupansi) | `tc-06-invalid-time-window.png`, `dashboard/tc06_prediction_chart.png`, `dashboard/tc06_invalid_window.png` |
| TC-07 | Otorisasi | Semua endpoint | Tidak ada operasi khusus; aturan otorisasi pada seluruh kontrak (kunci perangkat dan token dashboard) | Semua kontrak | Berlaku pada seluruh tahap | `tc-07-unauthorized-no-key.png`, `tc-07-unauthorized-wrong-credential.png` |
| TC-08 | Status tidak valid | `PUT /slots/{slot_id}/status` | `updateSlotStatus()` | SlotSensingService | Tahap 4: "Deteksi kendaraan & kirim status" (jalur gagal, `INVALID_STATUS`) | `tc-08-invalid-status.png` |
| TC-09 | Modul rekomendasi gagal | `POST /gate/entry-tap`, `GET /occupancy/floors`, `POST /dev/fault/recommendation` | `requestRecommendation()` (hasil `recommendationUnavailable`), `getFloorOccupancy()` | RecommendationService, OccupancyQueryService | Tahap 2: "Tampilkan lantai & slot, buka palang" (tampilan cadangan, palang tetap terbuka) | `tc-09-recommendation-failed.png`, `tc-09-recommendation-failed-gate.png` |

Catatan: `GET /slots`, `POST /dev/scenario/{name}`, dan `POST /dev/fault/recommendation` adalah endpoint pendukung di luar kontrak inti. Ketiganya dipakai untuk tampilan dan pengujian, bukan operasional.

## 2. Pemetaan fitur prototipe ke komponen dan TC

| Fitur | Masalah | Komponen | TC |
|---|---|---|---|
| Tap kartu dan validasi | P1 | Smart Gate, backend | TC-01, TC-03, TC-07 |
| Rekomendasi lantai dan slot | P1, P4 | Modul AI | TC-01, TC-02, TC-09 |
| Display gerbang | P1, P4 | Smart Gate | TC-01, TC-02, TC-03, TC-09 |
| Status slot real-time | P1, P3, P5 | Simulator, backend | TC-04, TC-05, TC-08 |
| LED tiga warna | P2 | Simulator, Smart Gate | TC-01, TC-04, TC-05 |
| Deteksi anomali dan UNKNOWN | P5 | Modul AI, backend | TC-05 |
| Peringatan sensor bermasalah ke pengelola | P3, P5 | Dashboard, backend | TC-05 |
| Dashboard okupansi | P3, P4 | Dashboard | TC-05 |
| Prediksi per jam | P3, P4 | Modul AI, dashboard | TC-06, TC-07 |
| Slot kosong saat motor keluar | P1, P3 | Simulator | TC-04 |

## 3. Cara mengulang pengujian sisi simulator

Jalankan backend, lalu pada terminal lain dari root repositori:

```bash
python -m simulator.scenarios.tc04_park_and_leave
python -m simulator.scenarios.tc05_sensor_fault              # tiga varian, sekitar 70 detik
python -m simulator.scenarios.tc05_sensor_fault --mode glitch # varian cepat
```

Setiap runner menulis log bertanda waktu ke `tests/evidence/`. Untuk demo manual:

```bash
python -m simulator.sensor_sim manual
# scenario peak_hour
# set F1-A20 occupied
# set F1-A20 free
# glitch F2-A12
```
