# pilih slot parkir terbaik: saring slot, beri nilai, lalu ambil yang tertinggi
import re

# bobot nilai (totalnya 1.0)
W_CAPACITY = 0.4    # sisa tempat kosong di lantai
W_PROXIMITY = 0.3   # seberapa dekat slot ke gerbang (nomor kecil = dekat)
W_BALANCE = 0.3     # supaya motor tersebar rata antar lantai
OVERLOAD_RATIO = 0.85  # lantai yang terisi 85% atau lebih dihindari kalau lantai lain masih longgar


def _slot_number(slot_id):
    # contoh: F2-A17 jadi 17, dipakai untuk mengukur kedekatan ke gerbang
    match = re.search(r"(\d+)$", slot_id)
    return int(match.group(1)) if match else 0


def recommend_slot(slots, floors):
    # pilih satu slot terbaik, atau None kalau tidak ada yang cocok
    # slots: [{slotId, floorNumber, status, distance}]
    # floors: [{floorNumber, isOpen, total}]
    open_floors = {f["floorNumber"]: f for f in floors if f.get("isOpen")}

    # aturan: hanya slot AVAILABLE di lantai yang dibuka, slot UNKNOWN tidak boleh dipilih
    candidates = [
        s for s in slots
        if s["status"] == "AVAILABLE" and s["floorNumber"] in open_floors
    ]
    if not candidates:
        return None

    # hitung per lantai: jumlah slot kosong dan seberapa penuh
    stats = {}
    for number, floor in open_floors.items():
        free = sum(1 for s in candidates if s["floorNumber"] == number)
        total = floor.get("total") or 1
        stats[number] = {"free": free, "total": total, "occupancy": 1 - free / total}

    floors_with_free = [n for n in stats if stats[n]["free"] > 0]
    # hindari lantai yang hampir penuh selama masih ada lantai lain yang longgar
    relaxed = [n for n in floors_with_free if stats[n]["occupancy"] < OVERLOAD_RATIO]
    allowed = relaxed if relaxed else floors_with_free
    min_occupancy = min(stats[n]["occupancy"] for n in allowed)

    best = None
    for slot in candidates:
        n = slot["floorNumber"]
        if n not in allowed:
            continue
        st = stats[n]
        capacity = st["free"] / st["total"]
        # nomor slot kecil = dekat gerbang = nilai besar
        proximity = 1 - (_slot_number(slot["slotId"]) - 1) / st["total"]
        balance = 1 - (st["occupancy"] - min_occupancy)
        score = W_CAPACITY * capacity + W_PROXIMITY * proximity + W_BALANCE * balance
        # nilai tertinggi yang dipilh, kalau nilai sama, maka pilih ID slot paling kecil 
        key = (-round(score, 6), slot["slotId"])
        if best is None or key < best[0]:
            best = (key, slot)

    chosen = best[1]
    return {"floorNumber": chosen["floorNumber"], "slotId": chosen["slotId"]}
