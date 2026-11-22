"""Otorisasi: perangkat memakai X-Device-Key, dashboard memakai Bearer token.

Nilai bisa diganti lewat variabel lingkungan; ini satu-satunya tempat kunci didefinisikan.
"""
import os

from fastapi import Header

from .errors import ApiError

DEVICE_KEY = os.getenv("PARKSENSE_DEVICE_KEY", "parksense-dev-key")
DASHBOARD_TOKEN = os.getenv("PARKSENSE_DASHBOARD_TOKEN", "dev-dashboard-token")


def _device_ok(key: str | None) -> bool:
    return key is not None and key == DEVICE_KEY


def _bearer_ok(authorization: str | None) -> bool:
    return authorization is not None and authorization == f"Bearer {DASHBOARD_TOKEN}"


def _unauthorized(msg: str) -> ApiError:
    return ApiError(401, "UNAUTHORIZED", msg)


def require_device(x_device_key: str | None = Header(default=None)) -> None:
    if not _device_ok(x_device_key):
        raise _unauthorized("Header X-Device-Key tidak ada atau salah")


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    if not _bearer_ok(authorization):
        raise _unauthorized("Bearer token tidak ada atau salah")


def require_any(
    x_device_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    if not (_device_ok(x_device_key) or _bearer_ok(authorization)):
        raise _unauthorized("Butuh X-Device-Key atau Bearer token yang valid")
