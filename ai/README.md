# Paket `ai/` — AI ParkSense

Fungsi Python yang dipanggil `backend/ai_adapter.py`.

| Berkas | Fungsi | Tujuan |
|---|---|---|
| `recommend.py` | `recommend_slot(slots, floors)` | Pilih slot terbaik atau `None` |
| `predict.py` | `predict_occupancy(time_window, history)`, `make_advisory(predictions, floors)` | Prediksi okupansi per jam per lantai + saran |
| `anomaly.py` | `detect_anomaly(reading, last_update, now)`, `status_from_distance(cm)` | Validasi sensor |
| `seed_history.py` | `load_history()` | Data riwayat tiruan (`history.json`) |

## 1. Rekomendasi slot
**Filter (aturan bisnis):** hanya slot `AVAILABLE` di lantai `isOpen`. `UNKNOWN` tidak pernah dipilih.

**Nilai gabungan** per slot kandidat:

```
nilai = 0.4 * kapasitas + 0.3 * kedekatan + 0.3 * balance
kapasitas = slot kosong lantai / total slot lantai
kedekatan = 1 - (nomor slot - 1) / total slot lantai   # A01 paling dekat gerbang
balance   = 1 - (okupansi lantai - okupansi lantai terendah)   # dorong ke lantai lebih longgar
```
Bobot ada sebagai konstanta `W_CAPACITY`, `W_PROXIMITY`, `W_BALANCE` di `recommend.py`.

**Hindari lantai yang hampir penuh:** lantai dengan okupansi >= 85% (`OVERLOAD_RATIO`) dibuang dari kandidat selama masih ada lantai lain yang < 85% dan punya slot kosong. Inilah yang membuat TC-01 (jam puncak) mengarah ke lantai 2.

**Kalau nilai sama:** nilai dibulatkan 6 desimal, lalu ID slot terkecil yang menang, jadi hasilnya selalu sama untuk data yang sama.

**Alasan model:** aturan berbobot mudah dijelaskan, dapat diaudit, tidak butuh data training.

## 2. Prediksi okupansi
- Prediksi = rata-rata `occupancyPercent` per (jam, lantai) dari 14 hari data. Nilai dijaga di 0..100.
- Rentang jam inklusif. Tidak valid (`fromHour >= toHour`, di luar 0..23, bukan integer) -> `ValueError`.
- `make_advisory`: bila puncak lantai terbuka >= 85% dan ada lantai tertutup -> sarankan membuka lantai tersebut lebih awal.

**Alasan model:** data riwayat hanya tiruan 14 hari, jadi model rumit tidak digunakan. Rata-rata sudah menangkap pola harian dan mudah dijelaskan. 

## 3. Anomali sensor
- Jarak valid 2..400 cm; di luar itu `OUT_OF_RANGE` (status slot -> `UNKNOWN`, LED `OFF`).
- Sensor tidak mengirim data lebih dari 60 detik (atau belum pernah kirim data sama sekali) -> `STALE` (sensor berhenti mengirim data).
- `status_from_distance`: < 30 cm `OCCUPIED`, selain itu `AVAILABLE`, di luar rentang `UNKNOWN`.

## 4. Data riwayat
`seed_history.py` membuat 14 hari kerja x 24 jam x 2 lantai (672 baris) dengan `random.Random(42)` (hasil selalu sama). Lantai 1 naik 06.30-09.00 dan penuh sekitar 07.30-11.00. Lantai 2 baru terisi setelah lantai 1 melewati 80%. Buat ulang: `python -m ai.seed_history`.

## 5. Menjalankan tes
```
python -m pytest tests/ai_tests -v
```

## Keterbatasan 
Data riwayat adalah tiruan, bukan data sensor nyata. Prediksi belum membedakan hari kerja dan akhir pekan.