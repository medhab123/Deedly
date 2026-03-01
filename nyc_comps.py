from flask import Flask, request, jsonify
import requests
import datetime as dt
import math

app = Flask(__name__)

# ---- Data sources (NYC Open Data / Socrata) ----
# PLUTO dataset id: 64uk-42ks
PLUTO_URL = "https://data.cityofnewyork.us/resource/64uk-42ks.json"
# NYC Citywide Rolling Calendar Sales dataset id: usep-8jbt
SALES_URL = "https://data.cityofnewyork.us/resource/usep-8jbt.json"

# Census geocoder (free) to get lat/lng from address
CENSUS_GEOCODER = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

# Optional: if you have an NYC Open Data app token, set it here to reduce throttling risk
SOCRATA_APP_TOKEN = None  # e.g. "YOUR_TOKEN"
COMMON_HEADERS = {"X-App-Token": SOCRATA_APP_TOKEN} if SOCRATA_APP_TOKEN else {}

def geocode_latlng(address: str):
    params = {
        "address": address,
        "benchmark": "Public_AR_Current",
        "format": "json",
    }
    r = requests.get(CENSUS_GEOCODER, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    matches = data.get("result", {}).get("addressMatches", [])
    if not matches:
        return None
    m = matches[0]
    coords = m["coordinates"]
    return {
        "matched_address": m.get("matchedAddress"),
        "lat": float(coords["y"]),
        "lng": float(coords["x"]),
    }

def socrata_get(url: str, params: dict):
    r = requests.get(url, params=params, headers=COMMON_HEADERS, timeout=25)
    r.raise_for_status()
    return r.json()

def parse_float(x):
    try:
        return float(x)
    except:
        return None

def parse_int(x):
    try:
        return int(float(x))
    except:
        return None

def months_ago_iso(months: int) -> str:
    # approximate months -> days for hackathon simplicity
    days = int(months * 30.4)
    d = dt.date.today() - dt.timedelta(days=days)
    return d.isoformat()

def find_subject_pluto_by_point(lat, lng, radius_m=80):
    # bounding box approximation (good enough for small radius)
    lat_delta = radius_m / 111_320.0
    lng_delta = radius_m / (111_320.0 * max(0.1, math.cos(math.radians(lat))))

    min_lat, max_lat = lat - lat_delta, lat + lat_delta
    min_lng, max_lng = lng - lng_delta, lng + lng_delta

    select = ",".join([
        "bbl","borough","block","lot","address","zipcode",
        "bldgclass","landuse","yearbuilt","bldgarea","unitsres","unitstotal",
        "numbldgs","council","cd","schooldist","latitude","longitude"
    ])

    where = (
        f"latitude between {min_lat} and {max_lat} "
        f"AND longitude between {min_lng} and {max_lng} "
        f"AND latitude is not null AND longitude is not null"
    )

    params = {
        "$select": select,
        "$where": where,
        "$limit": 100
    }

    rows = socrata_get(PLUTO_URL, params)

    # then keep your “pick closest using haversine” logic
        # pick the closest candidate by haversine distance
    best = None
    best_d = 1e18

    for row in rows:
        rlat = parse_float(row.get("latitude"))
        rlng = parse_float(row.get("longitude"))
        if rlat is None or rlng is None:
            continue

        d = haversine_meters(lat, lng, rlat, rlng)
        if d < best_d:
            best_d = d
            best = row

    if not best:
        return None

    return normalize_subject(best, approx_distance_m=best_d)

def normalize_subject(row: dict, approx_distance_m=None):
    return {
        "bbl": row.get("bbl"),
        "borough": row.get("borough"),
        "block": parse_int(row.get("block")),
        "lot": parse_int(row.get("lot")),
        "address": row.get("address"),
        "zipcode": row.get("zipcode"),
        "bldgclass": row.get("bldgclass"),
        "landuse": row.get("landuse"),
        "year_built": parse_int(row.get("yearbuilt")),
        "building_area_sqft": parse_int(row.get("bldgarea")),
        "res_units": parse_int(row.get("unitsres")),
        "total_units": parse_int(row.get("unitstotal")),
        "num_buildings": parse_int(row.get("numbldgs")),
        "school_district": row.get("schooldist"),
        "approx_distance_m": None if approx_distance_m is None else round(approx_distance_m, 1),
        "location": {
            "lat": parse_float(row.get("latitude")),
            "lng": parse_float(row.get("longitude")),
        }
    }

def haversine_meters(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def fetch_sales_comps(subject: dict, months: int, limit: int):
    """
    Strategy:
    1) comps in SAME borough + block, last N months, valid sale_price + gross_sqft
    2) if too few, widen to borough + zipcode (if present)
    """
    since = months_ago_iso(months)

    borough = subject.get("borough")
    block = subject.get("block")
    zipcode = subject.get("zipcode")

    def base_filters(extra_where: str):
        # Note: sales dataset uses sale_date, sale_price, gross_square_feet, borough, block, zip_code
        where = (
            f"sale_date >= '{since}T00:00:00.000' "
            f"AND sale_price > 10000 "
            f"AND gross_square_feet > 200 "
            f"AND {extra_where}"
        )
        return where

    # Attempt 1: same borough + block (most “comp-y” without geometry)
    where1 = base_filters(f"borough = '{borough}' AND block = {block}")
    params1 = {
        "$select": ",".join([
            "borough,neighborhood,building_class_category,building_class_at_time_of_sale",
            "address,zip_code,block,lot,",
            "gross_square_feet,land_square_feet,year_built,total_units,residential_units,commercial_units,",
            "sale_price,sale_date"
        ]),
        "$where": where1,
        "$order": "sale_date DESC",
        "$limit": limit
    }
    comps = socrata_get(SALES_URL, params1)

    # Fallback: borough + zipcode
    if len(comps) < max(3, min(6, limit)) and zipcode:
        where2 = base_filters(f"borough = '{borough}' AND zip_code = '{zipcode}'")
        params2 = dict(params1)
        params2["$where"] = where2
        params2["$limit"] = limit
        comps = socrata_get(SALES_URL, params2)

    return [normalize_comp(c) for c in comps]

def normalize_comp(c: dict):
    sale_price = parse_int(c.get("sale_price"))
    sqft = parse_int(c.get("gross_square_feet"))
    ppsf = None
    if sale_price and sqft and sqft > 0:
        ppsf = sale_price / sqft

    return {
        "borough": c.get("borough"),
        "neighborhood": c.get("neighborhood"),
        "address": c.get("address"),
        "zip_code": c.get("zip_code"),
        "block": parse_int(c.get("block")),
        "lot": parse_int(c.get("lot")),
        "sale_date": c.get("sale_date"),
        "sale_price": sale_price,
        "gross_sqft": sqft,
        "price_per_sqft": None if ppsf is None else round(ppsf, 2),
        "building_class_category": c.get("building_class_category"),
        "building_class_at_sale": c.get("building_class_at_time_of_sale"),
        "year_built": parse_int(c.get("year_built")),
        "total_units": parse_int(c.get("total_units")),
        "residential_units": parse_int(c.get("residential_units")),
        "commercial_units": parse_int(c.get("commercial_units")),
    }

def median(values):
    vals = sorted([v for v in values if v is not None])
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    if n % 2 == 1:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2

@app.get("/nyc/subject")
def nyc_subject():
    address = (request.args.get("address") or "").strip()
    if not address:
        return jsonify({"error": "Missing ?address=..."}), 400

    geo = geocode_latlng(address)
    if not geo:
        return jsonify({"error": "Could not geocode address"}), 404

    subject = find_subject_pluto_by_point(geo["lat"], geo["lng"])
    if not subject:
        return jsonify({"error": "No PLUTO lot found near this address", "geocode": geo}), 404

    return jsonify({"geocode": geo, "subject": subject})

@app.get("/nyc/comps")
def nyc_comps():
    address = (request.args.get("address") or "").strip()
    months = request.args.get("months", default=12, type=int)
    limit = request.args.get("limit", default=10, type=int)

    if not address:
        return jsonify({"error": "Missing ?address=..."}), 400

    geo = geocode_latlng(address)
    if not geo:
        return jsonify({"error": "Could not geocode address"}), 404

    subject = find_subject_pluto_by_point(geo["lat"], geo["lng"])
    if not subject:
        return jsonify({"error": "No PLUTO lot found near this address", "geocode": geo}), 404

    comps = fetch_sales_comps(subject, months=months, limit=limit)

    return jsonify({
        "geocode": geo,
        "subject": subject,
        "params": {"months": months, "limit": limit},
        "comp_count": len(comps),
        "comps": comps
    })

@app.get("/nyc/valuation")
def nyc_valuation():
    address = (request.args.get("address") or "").strip()
    months = request.args.get("months", default=12, type=int)

    if not address:
        return jsonify({"error": "Missing ?address=..."}), 400

    geo = geocode_latlng(address)
    if not geo:
        return jsonify({"error": "Could not geocode address"}), 404

    subject = find_subject_pluto_by_point(geo["lat"], geo["lng"])
    if not subject:
        return jsonify({"error": "No PLUTO lot found near this address", "geocode": geo}), 404

    comps = fetch_sales_comps(subject, months=months, limit=20)

    ppsfs = [c["price_per_sqft"] for c in comps if c.get("price_per_sqft")]
    med_ppsf = median(ppsfs)

    subj_sqft = subject.get("building_area_sqft")
    est_value = None
    if med_ppsf is not None and subj_sqft:
        est_value = int(med_ppsf * subj_sqft)

    # confidence: quick hack based on number of comps
    confidence = "low"
    if len(ppsfs) >= 10:
        confidence = "high"
    elif len(ppsfs) >= 5:
        confidence = "medium"

    return jsonify({
        "geocode": geo,
        "subject": subject,
        "months": months,
        "comps_used": len(ppsfs),
        "median_price_per_sqft": None if med_ppsf is None else round(med_ppsf, 2),
        "estimated_value": est_value,
        "confidence": confidence,
        "sample_comps": comps[:10]
    })

if __name__ == "__main__":
    # run on 5002 so it doesn't clash with your other APIs (5000, 5001)
    app.run(port=5002, debug=True)