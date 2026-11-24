# prediksi seberapa penuh parkiran tiap jam di tiap lantai, berdasarkan data riwayat

ADVISORY_THRESHOLD = 85.0  # batas persen terisi untuk memberi saran


def _validate_window(time_window):
    try:
        from_hour, to_hour = time_window
    except (TypeError, ValueError):
        raise ValueError("time_window harus (fromHour, toHour)")
    ok = all(isinstance(h, int) and not isinstance(h, bool) and 0 <= h <= 23
             for h in (from_hour, to_hour))
    if not ok or from_hour >= to_hour:
        raise ValueError("rentang jam tidak valid")
    return from_hour, to_hour


def predict_occupancy(time_window, history):
    # prediksi persen terisi untuk tiap jam (termasuk jam akhir) dan tiap lantai
    # history: [{date, hour, floorNumber, occupancyPercent}]
    from_hour, to_hour = _validate_window(time_window)

    # kelompokkan nilai per (jam, lantai)
    groups = {}
    for row in history:
        groups.setdefault((row["hour"], row["floorNumber"]), []).append(row["occupancyPercent"])
    floor_numbers = sorted({row["floorNumber"] for row in history})

    result = []
    for hour in range(from_hour, to_hour + 1):
        for floor in floor_numbers:
            values = groups.get((hour, floor), [])
            # prediksi = rata-rata dari semua hari (0 kalau tidak ada data)
            value = sum(values) / len(values) if values else 0.0
            result.append({
                "hour": hour,
                "floorNumber": floor,
                "predictedOccupancyPercent": round(value, 1),
            })
    return result


def make_advisory(predictions, floors):
    # kalimat saran untuk pengelola parkir
    if not predictions:
        return "Tidak ada data prediksi pada rentang jam ini."

    open_numbers = {f["floorNumber"] for f in floors if f.get("isOpen")}
    closed_numbers = sorted(f["floorNumber"] for f in floors if not f.get("isOpen"))

    # cari jam paling penuh di lantai yang sedang dibuka
    open_preds = [p for p in predictions if p["floorNumber"] in open_numbers] or predictions
    peak = max(open_preds, key=lambda p: (p["predictedOccupancyPercent"], -p["hour"]))
    pct = peak["predictedOccupancyPercent"]
    hour_text = f"{peak['hour']:02d}.00"

    if pct >= ADVISORY_THRESHOLD and closed_numbers:
        return (f"Lantai {peak['floorNumber']} diperkirakan terisi {pct:.0f}% pada pukul {hour_text}. "
                f"Disarankan membuka lantai {closed_numbers[0]} lebih awal.")
    if pct >= ADVISORY_THRESHOLD:
        return (f"Lantai {peak['floorNumber']} diperkirakan terisi {pct:.0f}% pada pukul {hour_text}. "
                "Semua lantai sudah terbuka, siapkan petugas untuk mengarahkan pengemudi.")
    return (f"Parkiran diperkirakan masih aman (paling penuh {pct:.0f}% "
            f"pada pukul {hour_text}). Belum perlu membuka lantai tambahan.")
