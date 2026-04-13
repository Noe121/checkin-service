"""Geofence verification helpers.

Used by POST /api/checkin/events/{event_id}/checkin to validate that
the submitted lat/lon is within the event's geofence radius.

Two design choices baked into this module:
  1. Coordinates are NEVER persisted at full precision. Before hashing
     for the audit row we round to ~100m precision (3 decimal places of
     lat/lon ≈ 110m at the equator) so the resulting `lat_hash` /
     `lon_hash` does not uniquely identify the attendee's exact location.
  2. The haversine distance is computed in floating point on the FULL
     submitted coordinates (no rounding) so the verification itself is
     accurate to ~1m. Rounding only happens for the *stored hash*, not
     for the *check*.
"""
from __future__ import annotations

import math
from typing import Optional

from .hashing import hash_pii

_EARTH_RADIUS_M = 6_371_000.0  # WGS84 mean earth radius in meters
_HASH_PRECISION_DIGITS = 3  # 3 decimal places ~= 110m at equator
_MAX_GEOFENCE_RADIUS_M = 5000  # app-layer cap (also enforced by schema validators)


def haversine_distance_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Great-circle distance in meters between two (lat, lon) points."""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return _EARTH_RADIUS_M * c


def round_for_hash(value: float) -> float:
    """Round a coordinate to ~100m precision before hashing.

    Defends against the case where an attacker who somehow obtained the
    HMAC key and the hashed audit log row could brute-force the original
    coordinate by trying every possible (lat, lon) pair to ~1m. With
    rounding, the search space is also coarsened to ~100m grid cells.
    """
    return round(value, _HASH_PRECISION_DIGITS)


def hash_coordinate(value: Optional[float]) -> Optional[str]:
    """Round + hash a coordinate. None passes through."""
    if value is None:
        return None
    return hash_pii(round_for_hash(value))


class GeofenceCheckResult:
    """Result of a geofence check."""

    def __init__(
        self,
        *,
        passed: bool,
        distance_m: Optional[float] = None,
        reason: Optional[str] = None,
    ) -> None:
        self.passed = passed
        self.distance_m = distance_m
        self.reason = reason

    @property
    def ok(self) -> bool:
        return self.passed


def verify_distance(
    *,
    submitted_lat: Optional[float],
    submitted_lon: Optional[float],
    event_lat: Optional[float],
    event_lon: Optional[float],
    radius_m: Optional[int],
) -> GeofenceCheckResult:
    """Verify the submitted coordinates are within the event geofence.

    Returns a GeofenceCheckResult — caller checks `.ok` and reads
    `.distance_m` / `.reason` for diagnostics.
    """
    # Both sides must have coordinates to perform a check.
    if submitted_lat is None or submitted_lon is None:
        return GeofenceCheckResult(passed=False, reason="missing_submitted_coords")
    if event_lat is None or event_lon is None:
        return GeofenceCheckResult(passed=False, reason="missing_event_coords")

    # Defensive bounds check (the schema layer also validates these).
    if not (-90.0 <= submitted_lat <= 90.0 and -180.0 <= submitted_lon <= 180.0):
        return GeofenceCheckResult(passed=False, reason="submitted_coords_out_of_range")
    if not (-90.0 <= event_lat <= 90.0 and -180.0 <= event_lon <= 180.0):
        return GeofenceCheckResult(passed=False, reason="event_coords_out_of_range")

    effective_radius = radius_m or 100
    if effective_radius <= 0 or effective_radius > _MAX_GEOFENCE_RADIUS_M:
        return GeofenceCheckResult(passed=False, reason="invalid_radius")

    distance = haversine_distance_m(
        float(submitted_lat),
        float(submitted_lon),
        float(event_lat),
        float(event_lon),
    )
    return GeofenceCheckResult(
        passed=distance <= effective_radius,
        distance_m=distance,
        reason=None if distance <= effective_radius else "out_of_range",
    )
