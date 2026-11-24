# Tabel Pengujian Prototipe ParkSense (Deliverable 3)

Kolom **Hasil Aktual**, **Status**, dan **Bukti** diisi setelah TC dijalankan.
Bukti disimpan di `tests/evidence/` (nama berkas ditulis di kolom Bukti).

| ID | Skenario | Langkah / Input | Hasil Diharapkan | Hasil Aktual | Status (Lulus/Gagal) | Bukti |
|---|---|---|---|---|---|---|
| TC-01 | Tap kartu valid pada jam puncak | 1. `POST /dev/scenario/peak_hour` 2. `POST /gate/entry-tap` dengan `cardId: RFID-04A1B7C2` | 200; rekomendasi lantai 2 (slot AVAILABLE valid); `gateAction: OPEN_BARRIER`; LED slot rekomendasi YELLOW di `GET /slots` dan peta slot gerbang | | | |
| TC-02 | Semua lantai yang dibuka penuh | 1. `POST /dev/scenario/all_full` 2. `POST /gate/entry-tap` kartu valid | 200; `recommendation: null`; display menampilkan info penuh; palang tetap terbuka (`OPEN_BARRIER`) | | | |
| TC-03 | Kartu tidak valid | `POST /gate/entry-tap` dengan `cardId` tidak terdaftar (mis. `RFID-XXXX`) | 400 `INVALID_CARD`; palang tidak terbuka; display menampilkan penolakan | | | |
| TC-04 | Motor parkir lalu keluar | 1. `PUT /slots/F1-A05/status` status `OCCUPIED` 2. `GET /occupancy/floors` 3. PUT status `AVAILABLE` 4. `GET /occupancy/floors` | LED RED lalu GREEN; `available` lantai 1 berkurang 1 lalu kembali | | | |
| TC-05 | Sensor bermasalah | a) Simulator `stop F2-A17` lalu tunggu > 60 detik, atau b) kirim `rawSensorValue: 500` | Slot UNKNOWN, LED OFF, tidak direkomendasikan, dihitung di `unknown` pada `GET /occupancy/floors`, peringatan muncul di dashboard | | | |
| TC-06 | Prediksi okupansi jam puncak | 1. `GET /ai/predictions/occupancy?fromHour=6&toHour=9` 2. Ulangi dengan `fromHour=9&toHour=6` | 1) 200: prediksi per jam per lantai + `advisory` 2) 400 `INVALID_TIME_WINDOW` | | | |
| TC-07 | Otorisasi | Panggil endpoint tanpa header kunci / dengan kunci salah | 401 dengan format galat seragam | | | |
| TC-08 | Status tidak valid | `PUT /slots/F1-A01/status` dengan `status: "BROKEN"` | 400 `INVALID_STATUS` | | | |
| TC-09 | Modul rekomendasi gagal | 1. `POST /dev/fault/recommendation?enabled=true` 2. Tap kartu valid 3. Pulihkan `enabled=false` | 500 `RECOMMENDATION_FAILED`; `gateAction: OPEN_BARRIER` tetap; display menampilkan ketersediaan per lantai (`floors`) | | | |

## Sumber bukti per TC

| TC | Bukti API (respons/log) | Bukti tampilan |
|---|---|---|
| TC-01 | `run_all.py` / Swagger | Halaman gerbang (layar + LED kuning) |
| TC-02 | `run_all.py` / Swagger | Halaman gerbang (info penuh) |
| TC-03 | `run_all.py` / Swagger | Halaman gerbang (penolakan) |
| TC-04 | Log runner simulator | Panel LED simulator + dashboard |
| TC-05 | Log runner simulator | Dashboard (peringatan sensor) |
| TC-06 | `run_all.py` / Swagger | Dashboard (grafik + advisory + pesan galat) |
| TC-07 | `run_all.py` / Swagger | – |
| TC-08 | `run_all.py` / Swagger | – |
| TC-09 | `run_all.py` / Swagger | Halaman gerbang (palang terbuka + ketersediaan per lantai) |