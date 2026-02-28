from flask import Flask, request, jsonify
import requests
import math

app = Flask(__name__)

# NCES EDGE public school locations (ArcGIS REST)
NCES_PUBLIC_SCHOOLS_QUERY = (
    "https://nces.ed.gov/opengis/rest/services/K12_School_Locations/"
    "EDGE_GEOCODE_PUBLICSCH_2223/MapServer/0/query"
)

def miles_to_meters(mi: float) -> float:
    return mi * 1609.344

def haversine_miles(lat1, lon1, lat2, lon2) -> float:
    R_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    km = R_km * c
    return km * 0.621371

def fetch_nces_public_schools_near(lat: float, lng: float, radius_miles: float, limit: int):
    params = {
        "f": "json",
        "where": "1=1",
        "geometry": f"{lng},{lat}",          # lon,lat
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": miles_to_meters(radius_miles),
        "units": "esriSRUnit_Meter",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "resultRecordCount": limit,
    }

    r = requests.get(NCES_PUBLIC_SCHOOLS_QUERY, params=params, timeout=25)
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
            dist = haversine_miles(lat, lng, slat, slng)

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

    schools.sort(key=lambda s: (s["distance_miles"] is None, s["distance_miles"] or 999999))
    return schools

@app.get("/schools")
def schools():
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    radius_miles = request.args.get("radius_miles", default=2.0, type=float)
    limit = request.args.get("limit", default=10, type=int)

    if lat is None or lng is None:
        return jsonify({"error": "Missing lat/lng. Example: /schools?lat=38.9&lng=-77.03&radius_miles=2"}), 400

    try:
        results = fetch_nces_public_schools_near(lat, lng, radius_miles, limit)
        return jsonify({
            "query": {"lat": lat, "lng": lng, "radius_miles": radius_miles, "limit": limit},
            "count": len(results),
            "schools": results
        })
    except Exception as e:
        return jsonify({"error": "Failed to fetch schools", "details": str(e)}), 500

if __name__ == "__main__":
    app.run(port=5001, debug=True)