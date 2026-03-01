"""
NCES EDGE public school locations — nearby schools by lat/lng.
Uses ArcGIS REST API (no key required). Async via httpx.
"""

import math
from typing import Any

import httpx

NCES_PUBLIC_SCHOOLS_QUERY = (
    "https://nces.ed.gov/opengis/rest/services/K12_School_Locations/"
    "EDGE_GEOCODE_PUBLICSCH_2223/MapServer/0/query"
)


def _miles_to_meters(mi: float) -> float:
    return mi * 1609.344


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R_km * c * 0.621371


async def fetch_nces_public_schools_near(
    lat: float,
    lng: float,
    radius_miles: float = 2.0,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Fetch public schools near a point from NCES EDGE.
    Returns list of school dicts with name, address, grades, level, location, distance_miles.
    """
    params = {
        "f": "json",
        "where": "1=1",
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": _miles_to_meters(radius_miles),
        "units": "esriSRUnit_Meter",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "resultRecordCount": limit,
    }
    async with httpx.AsyncClient(timeout=25.0) as client:
        r = await client.get(NCES_PUBLIC_SCHOOLS_QUERY, params=params)
        r.raise_for_status()
        data = r.json()

    if "error" in data:
        raise RuntimeError(f"NCES error: {data['error']}")

    features = data.get("features", [])
    schools = []
    for ft in features:
        attrs = ft.get("attributes", {}) or {}
        geom = ft.get("geometry", {}) or {}
        slat = geom.get("y")
        slng = geom.get("x")
        dist = None
        if slat is not None and slng is not None:
            dist = _haversine_miles(lat, lng, slat, slng)
        schools.append({
            "name": attrs.get("NAME"),
            "nces_school_id": attrs.get("NCESSCH"),
            "address": {
                "street": attrs.get("STREET"),
                "city": attrs.get("CITY"),
                "state": attrs.get("STATE"),
                "zip": attrs.get("ZIP"),
            },
            "grades": {
                "low": attrs.get("GRADELOW"),
                "high": attrs.get("GRADEHIGH"),
            },
            "level": attrs.get("LEVEL"),
            "location": {"lat": slat, "lng": slng},
            "distance_miles": None if dist is None else round(dist, 3),
        })
    schools.sort(
        key=lambda s: (s["distance_miles"] is None, s["distance_miles"] or 999999)
    )
    return schools
