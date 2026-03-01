"""
Geocoding service using Census Geocoder (free, no key required).
Converts a one-line address -> lat, lng, tract GEOID, state/county FIPS.

This mirrors the working logic from your Flask `app.py`:
- Uses `geographies/onelineaddress` with the full address string
- Reads GEOID from the `Census Tracts` geography block
"""

import httpx
from typing import Optional


async def geocode_address(address: str) -> Optional[dict]:
    """
    Geocode address using Census Geocoder one-line endpoint.
    Returns: { lat, lng, tract, state_fips, county_fips, full_geoid, matched_address } or None
    """
    full_address = address.strip()
    if not full_address:
        return None

    base = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
    params = {
        "address": full_address,
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "format": "json",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(base, params=params)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return None

    matches = data.get("result", {}).get("addressMatches", [])
    if not matches:
        return None

    m = matches[0]
    coords = m.get("coordinates", {})
    geos = m.get("geographies", {})
    tracts = geos.get("Census Tracts", []) or []
    tract_info = tracts[0] if tracts else {}
    addr_components = m.get("addressComponents", {}) or {}

    return {
        "lat": coords.get("y"),
        "lng": coords.get("x"),
        "tract": tract_info.get("TRACT", ""),
        "state_fips": tract_info.get("STATE", ""),
        "county_fips": tract_info.get("COUNTY", ""),
        "full_geoid": tract_info.get("GEOID", ""),
        "zip_code": addr_components.get("zip"),
        "matched_address": m.get("matchedAddress", full_address),
    }
