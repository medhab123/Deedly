from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

CENSUS_GEOCODER = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
ACS_ENDPOINT = "https://api.census.gov/data/2022/acs/acs5"  # stable + widely available

def geocode_with_tract(address: str):
    """
    Uses the Census Geocoder 'geographies/onelineaddress' endpoint to get:
    - standardized matched address
    - lat/lng
    - GEOIDs including Census Tract (state+county+tract)
    """
    params = {
        "address": address,
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
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
    geos = m.get("geographies", {})

    # In most cases you'll find tract under "Census Tracts"
    tracts = geos.get("Census Tracts", [])
    if not tracts:
        # fallback: sometimes called "Census Tracts" anyway; if missing, return without tract
        tract_geoid = None
    else:
        tract_geoid = tracts[0].get("GEOID")

    return {
        "matched_address": m.get("matchedAddress"),
        "lat": coords.get("y"),
        "lng": coords.get("x"),
        "tract_geoid": tract_geoid,
    }

def acs_demographics_for_tract(tract_geoid: str):
    """
    Pull a few buyer-relevant ACS variables at tract level:
    - B19013_001E: Median household income
    - B01003_001E: Total population
    - B25077_001E: Median home value
    """
    state = tract_geoid[0:2]
    county = tract_geoid[2:5]
    tract = tract_geoid[5:11]

    vars_ = ["B19013_001E", "B01003_001E", "B25077_001E"]
    params = {
        "get": ",".join(["NAME"] + vars_),
        "for": f"tract:{tract}",
        "in": f"state:{state} county:{county}",
        # You can add &key=YOUR_KEY later. It works without a key for small usage.
    }

    r = requests.get(ACS_ENDPOINT, params=params, timeout=20)
    r.raise_for_status()
    rows = r.json()

    # rows[0] = header, rows[1] = values
    header = rows[0]
    values = rows[1]
    obj = dict(zip(header, values))

    def to_int(x):
        try:
            return int(float(x))
        except:
            return None

    return {
        "tract_name": obj.get("NAME"),
        "median_household_income": to_int(obj.get("B19013_001E")),
        "population": to_int(obj.get("B01003_001E")),
        "median_home_value": to_int(obj.get("B25077_001E")),
        "state": obj.get("state"),
        "county": obj.get("county"),
        "tract": obj.get("tract"),
    }

@app.get("/enrich")
def enrich():
    address = request.args.get("address", "").strip()
    if not address:
        return jsonify({"error": "Missing ?address=..."}), 400

    geo = geocode_with_tract(address)
    if not geo:
        return jsonify({"error": "No match found for address"}), 404

    if not geo["tract_geoid"]:
        return jsonify({
            "address": geo,
            "warning": "Matched address, but tract GEOID not found in response"
        })

    demo = acs_demographics_for_tract(geo["tract_geoid"])

    # Simple “buyer POV” summary (you can later replace w/ LLM)
    summary = []
    if demo["median_household_income"] is not None:
        summary.append(f"Median household income around here is about ${demo['median_household_income']:,}.")
    if demo["median_home_value"] is not None:
        summary.append(f"Median home value in this tract is about ${demo['median_home_value']:,}.")
    if demo["population"] is not None:
        summary.append(f"Tract population is ~{demo['population']:,} people.")

    return jsonify({
        "deedly": {
            "matched": geo["matched_address"],
            "lat": geo["lat"],
            "lng": geo["lng"],
            "tract_geoid": geo["tract_geoid"],
        },
        "enrichment": demo,
        "buyer_summary": " ".join(summary)
    })

if __name__ == "__main__":
    app.run(port=5000, debug=True)