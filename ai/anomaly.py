# cek apakah data sensor bermasalah, dan ubah jarak sensor jadi status slot

MIN_DISTANCE_CM = 2        # kurang dari ini = sensor rusak
MAX_DISTANCE_CM = 400      # lebih dari ini = sensor rusak
OCCUPIED_BELOW_CM = 30     # jarak kurang dari 30 cm = ada motor
STALE_SECONDS = 60         # sensor tidak mengirim data lebih dari 60 detik = dianggap berhenti kirim data


def _get_distance(reading):
    # backend mengirim laporan sensor berbentuk dict: {"rawSensorValue": 18.4, "unit": "cm", ...}
    # fungsi ini menerima angka biasa (cm) atau None
    if isinstance(reading, dict):
        return reading.get("rawSensorValue")
    return reading


def status_from_distance(cm):
    # ubah jarak sensor (cm) jadi status slot
    if cm is None or cm < MIN_DISTANCE_CM or cm > MAX_DISTANCE_CM:
        return "UNKNOWN"
    return "OCCUPIED" if cm < OCCUPIED_BELOW_CM else "AVAILABLE"


def detect_anomaly(reading, last_update, now):
    # hasilnya salah satu dari: "OK", "OUT_OF_RANGE" (jarak di luar batas), atau "STALE" (sensor berhenti mengirim data)
    # reading: laporan sensor (dict dengan rawSensorValue) atau jarak dalam cm
    # last_update, now: waktu update terakhir dan waktu sekarang (datetime)
    distance = _get_distance(reading)

    # cek jarak dulu, karena nilai di luar 2..400 cm jelas salah
    if distance is not None and not (MIN_DISTANCE_CM <= distance <= MAX_DISTANCE_CM):
        return "OUT_OF_RANGE"
    # sensor yang belum pernah kirim data sama sekali juga dianggap berhenti kirim data
    if last_update is None or (now - last_update).total_seconds() > STALE_SECONDS:
        return "STALE"
    return "OK"
