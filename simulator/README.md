# Simulator IoT ParkSense (`simulator/`)

Simulator ini menggantikan perangkat fisik di gedung parkir: **gateway ESP32 + sensor ultrasonik** per slot dan **LED** penunjuk slot. Ia memanggil `PUT /slots/{slot_id}/status` dengan payload yang persis sama dengan perangkat nyata (kontrak AGENTS.md Bagian 4), jadi backend tidak bisa membedakan simulator dari perangkat sungguhan.

| Perangkat nyata | Di simulator |
|---|---|
| Sensor ultrasonik per slot | Nilai jarak (cm): terisi 10-25 cm, kosong 80-200 cm, rusak 500 cm |
| Gateway ESP32 per lantai | `gatewayId = ESP32-GW-F1` / `ESP32-GW-F2` |
| LED slot | Panel berwarna di terminal, diperbarui dari `ledCommand` balasan backend |

## Struktur

```
simulator/
  config.py               URL, X-Device-Key, ambang sensor, STALE/HEARTBEAT (satu tempat)
  sensor_sim.py           simulator: mode manual, auto, fault, LED virtual, heartbeat
  scenarios/
    common.py             log bukti bertanda waktu ke tests/evidence/
    run_scenario.py       pemanggil POST /dev/scenario/{name}
    tc04_park_and_leave.py  runner TC-04
    tc05_sensor_fault.py    runner TC-05
  tests/
    mock_backend.py       backend tiruan khusus uji simulator (bukan pengganti backend/)
    test_sensor_sim.py    pytest
```

## Persiapan

Dari root repo (Python 3.11+; hanya butuh `requests`, sudah dipakai tim):

```bash
pip install requests pytest
python -m uvicorn backend.main:app --reload --port 8000   # terminal 1: backend
```

URL dan kunci bisa diganti lewat variabel lingkungan tanpa mengubah kode: `PARKSENSE_URL`, `PARKSENSE_DEVICE_KEY`, `STALE_SECONDS`, `HEARTBEAT_SECONDS`.

## Cara pakai

### Mode manual (dipakai saat demo)

```bash
python -m simulator.sensor_sim manual
```

| Perintah | Arti |
|---|---|
| `scenario peak_hour` | muat kondisi awal di backend (`reset`, `peak_hour`, `all_full`, `sensor_stale`), lalu ambil alih semua slot agar ikut heartbeat |
| `set F2-A17 occupied` | motor parkir (jarak acak 10-25 cm). Bisa beri jarak: `set F2-A17 occupied 15` |
| `set F2-A17 free` | motor keluar (jarak acak 80-200 cm) |
| `stop F2-A17` | sensor berhenti melapor; setelah > 60 dtk backend menandai UNKNOWN (STALE) |
| `resume F2-A17` | sensor melapor lagi |
| `glitch F2-A17` | sensor rusak, kirim 500 cm -> UNKNOWN + LED OFF (`anomaly: OUT_OF_RANGE`) |
| `panel` | panel LED terkini dari `GET /slots` (termasuk kuning hasil tap gerbang) |
| `floors` | ringkasan `GET /occupancy/floors` |
| `heartbeat` | daftar slot yang masih dikirim ulang |
| `adopt` | ambil alih semua slot AVAILABLE/OCCUPIED tanpa memuat skenario |
| `quit` | keluar |

### Mode auto (lalu lintas acak pola jam puncak)

```bash
python -m simulator.sensor_sim auto --speed 60 --start-hour 6 --tap
```

- `--speed 60`: 1 detik nyata = 1 menit simulasi (06.00-09.00 selesai dalam 3 menit).
- Kedatangan memuncak 06.30-09.00, kepergian naik setelah 12.00 (tabel `ARRIVALS_PER_HOUR` dan `DEPART_FRACTION_PER_HOUR` di `sensor_sim.py`).
- `--tap`: tiap motor tap kartu valid di gerbang (`POST /gate/entry-tap`) lalu parkir di slot rekomendasi. Tanpa `--tap`, motor memilih slot AVAILABLE sendiri di lantai terbuka, lantai bawah dulu.
- Opsi lain: `--duration 120` (batas detik nyata), `--seed 1` (bisa diulang), `--no-clear`, `--no-adopt`.

### Mode fault dan perintah sekali jalan

```bash
python -m simulator.sensor_sim fault glitch F2-A17            # 500 cm
python -m simulator.sensor_sim fault stop F2-A17 --keep F2-A18 # tunggu > STALE, lalu tampilkan hasil
python -m simulator.sensor_sim set F1-A05 occupied            # satu laporan (tanpa heartbeat)
python -m simulator.sensor_sim scenario peak_hour
python -m simulator.sensor_sim panel
```

Tambahkan `--no-color` bila terminal tidak menampilkan warna. Windows Terminal/PowerShell modern sudah mendukung warna.

## Heartbeat (penting)

Backend menandai slot UNKNOWN bila tidak ada laporan > 60 detik (`STALE_SECONDS`). Karena itu simulator menjalankan thread latar yang **mengirim ulang bacaan terakhir tiap 20 detik** (`HEARTBEAT_SECONDS`, harus <= 30) untuk semua slot yang pernah melapor. Perintah `stop` hanya mengeluarkan satu slot dari heartbeat; itulah yang memicu STALE di TC-05, sementara slot lain tetap segar.

Untuk demo panjang, backend boleh dijalankan dengan `STALE_SECONDS=600`. Set juga variabel yang sama di terminal simulator supaya pesan dan waktu tunggu runner ikut menyesuaikan.

## Runner kasus uji (bukti ke `tests/evidence/`)

Setiap runner menulis log bertanda waktu, misalnya `tests/evidence/TC-04_20261124-220413.log`, berisi langkah, respons HTTP mentah, hasil tiap cek (LULUS/GAGAL), dan ringkasan akhir. Kode keluar 0 bila semua cek lulus.

```bash
python -m simulator.scenarios.tc04_park_and_leave              # TC-04, slot bawaan F1-A05
python -m simulator.scenarios.tc05_sensor_fault                # TC-05 semua varian (~65 dtk)
python -m simulator.scenarios.tc05_sensor_fault --mode glitch  # varian cepat
python -m simulator.scenarios.run_scenario peak_hour           # muat skenario + log kondisi awal
```

**TC-04**: `reset` -> PUT 15 cm (cek OCCUPIED, LED RED, `available` lantai berkurang 1) -> PUT 150 cm (cek AVAILABLE, LED GREEN, `available` kembali).

**TC-05** punya tiga varian:
- `glitch`: `all_full`, lalu satu slot dikosongkan (sehat) dan satu slot dikirimi 500 cm. Cek `anomaly: OUT_OF_RANGE`, UNKNOWN, LED OFF, `unknown` dihitung terpisah, dan tap kartu valid harus merekomendasikan slot sehat, bukan slot rusak.
- `scenario`: memakai `POST /dev/scenario/sensor_stale` dari backend.
- `stale`: sensor sungguh berhenti. Slot target di-`stop`, slot pembanding tetap di-heartbeat, tunggu `STALE_SECONDS + 5`. Target harus UNKNOWN + OFF, pembanding tetap OCCUPIED.

Peringatan sensor di dashboard (sisi TC-05 milik dashboard) membaca data yang sama dari `GET /slots`; tangkapan layarnya diambil dari halaman dashboard.

## Pengujian

```bash
python -m pytest simulator -q
```

Tes memakai `simulator/tests/mock_backend.py`, backend tiruan kecil di port acak, jadi bisa dijalankan tanpa backend asli dan tidak bentrok dengan port 8000. Backend tiruan bisa juga dijalankan manual untuk mencoba simulator: `python -m simulator.tests.mock_backend --port 8000`. Bukti resmi TC-04/TC-05 tetap harus diambil terhadap backend asli.

## Hal yang perlu dicek saat integrasi dengan backend

1. Nilai `sensorType` (`ULTRASONIC`) dan `vehicleType` (`MOTORCYCLE`) tidak ditetapkan enumnya di kontrak. Bila backend memvalidasi nilai lain, ubah konstanta `SENSOR_TYPE` / `VEHICLE_TYPE` di `sensor_sim.py`.
2. Heartbeat mengirim ulang `AVAILABLE` untuk slot kosong. Pastikan backend tetap mempertahankan warna YELLOW untuk slot rekomendasi yang masih dalam 120 detik walaupun menerima laporan AVAILABLE ulang; jika tidak, LED kuning TC-01 bisa hilang saat simulator berjalan.
3. Varian `glitch` TC-05 mengandalkan skenario `all_full` mengisi semua slot. Bila skenario backend berbeda, cek "rekomendasi jatuh ke satu-satunya slot sehat" bisa gagal walaupun slot rusak tetap tidak direkomendasikan.

## Keterbatasan

Sensor, gateway, dan LED sepenuhnya disimulasikan; pola kedatangan di mode auto adalah tabel sederhana, bukan data nyata. MQTT belum diimplementasikan (opsional di AGENTS.md).
