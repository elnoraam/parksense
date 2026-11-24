"""Pemanggil POST /dev/scenario/{name} dengan log bukti.

Contoh: python -m simulator.scenarios.run_scenario peak_hour
"""
import sys

from simulator.scenarios.common import EvidenceLog, base_parser, load_scenario
from simulator.sensor_sim import SCENARIOS, ApiClient, ApiUnavailable


def main(argv=None) -> int:
    p = base_parser("Muat kondisi awal backend lewat POST /dev/scenario/{name}")
    p.add_argument("name", choices=SCENARIOS)
    args = p.parse_args(argv)
    api = ApiClient(args.url, args.key)
    log = EvidenceLog(f"scenario-{args.name}", f"Memuat skenario {args.name}", args.evidence_dir,
                      base_url=args.url)
    try:
        if load_scenario(api, log, args.name):
            # Ringkasan per lantai sesudah skenario dimuat, sebagai bukti kondisi awal
            code, body = api.get_floors()
            log.http("GET /occupancy/floors", code, body)
            for f in body.get("floors", []):
                log.write(f"Lantai {f['floorNumber']} ({'buka' if f['isOpen'] else 'tutup'}): "
                          f"available={f['available']} occupied={f['occupied']} unknown={f['unknown']}")
    except ApiUnavailable as exc:
        log.check("backend dapat dihubungi", False, str(exc))
    return log.finish()


if __name__ == "__main__":
    sys.exit(main())
