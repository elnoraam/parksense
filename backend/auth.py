"""Otorisasi: perangkat memakai X-Device-Key, dashboard memakai Bearer token.

Nilai bisa diganti lewat variabel lingkungan; ini satu-satunya tempat kunci didefinisikan.
"""
import os

from fastapi import Depends
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from .errors import ApiError

DEVICE_KEY = os.getenv("PARKSENSE_DEVICE_KEY", "parksense-dev-key")
DASHBOARD_TOKEN = os.getenv("PARKSENSE_DASHBOARD_TOKEN", "dev-dashboard-token")

# Skema keamanan dideklarasikan agar Swagger (/docs) menampilkan tombol Authorize.
# Swagger mengabaikan parameter header biasa bernama "Authorization", jadi tanpa ini
# token dashboard tidak pernah terkirim dari /docs. auto_error=False: galat 401 tetap
# memakai format seragam dari _unauthorized.
device_scheme = APIKeyHeader(name="X-Device-Key", scheme_name="DeviceKey", auto_error=False)
bearer_scheme = HTTPBearer(scheme_name="DashboardBearer", auto_error=False)


def _device_ok(key: str | None) -> bool:
    return key is not None and key == DEVICE_KEY


def _bearer_ok(credentials: HTTPAuthorizationCredentials | None) -> bool:
    return credentials is not None and credentials.credentials == DASHBOARD_TOKEN


def _unauthorized(msg: str) -> ApiError:
    return ApiError(401, "UNAUTHORIZED", msg)


def require_device(x_device_key: str | None = Depends(device_scheme)) -> None:
    if not _device_ok(x_device_key):
        raise _unauthorized("Header X-Device-Key tidak ada atau salah")


def require_bearer(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    if not _bearer_ok(credentials):
        raise _unauthorized("Bearer token tidak ada atau salah")


def require_any(
    x_device_key: str | None = Depends(device_scheme),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    if not (_device_ok(x_device_key) or _bearer_ok(credentials)):
        raise _unauthorized("Butuh X-Device-Key atau Bearer token yang valid")
