from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import json

app = FastAPI()

class AddressRequest(BaseModel):
    address: str

#STEP 1: Address → GPS Coordinates
def geocode_address(address):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address, "format": "json", "limit": 1}
    headers = {"User-Agent": "TitleLens/1.0"}
    data = requests.get(url, params=params, headers=headers).json()
    if not data:
        raise ValueError("Could not geocode address")
    return float(data[0]["lat"]), float(data[0]["lon"])

# STEP 2: GPS → Census Tract GEOID
def get_census_tract(lat, lon):
    url = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
    params = {
        "x": lon, "y": lat,
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "format": "json"
    }
    data = requests.get(url, params=params).json()
    tracts = data["result"]["geographies"].get("Census Tracts", [])
    if not tracts:
        raise ValueError("No census tract found")
    return tracts[0]["GEOID"]

# STEP 3: Census Tract → FEMA NRI Data (via ArcGIS)
def get_fema_risk(tract_geoid):
    url = "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/National_Risk_Index_Census_Tracts/FeatureServer/0/query"
    params = {
        "where": f"TRACTFIPS='{tract_geoid}'",
        "outFields": "*",
        "returnGeometry": "false",
        "f": "json"
    }
    response = requests.get(url, params=params)
    data = response.json()

    if "error" in data:
        raise ValueError(f"ArcGIS error: {data['error']}")

    features = data.get("features", [])
    if not features:
        raise ValueError(f"No FEMA data found for tract {tract_geoid}")

    return features[0]["attributes"]

# ENDPOINT: POST /risk-report
@app.post("/risk-report")
def risk_report(body: AddressRequest):
    try:
        lat, lon = geocode_address(body.address)
        tract    = get_census_tract(lat, lon)
        fema     = get_fema_risk(tract)

        return {
            "address":              body.address,
            "tract":                tract,
            "county":               fema.get("COUNTY"),
            "state":                fema.get("STATEABBRV"),
            "overall_score":        fema.get("RISK_SCORE"),
            "overall_rating":       fema.get("RISK_RATNG"),
            "wildfire_score":       fema.get("WFIR_RISKS"),
            "wildfire_rating":      fema.get("WFIR_RISKR"),
            "flood_score":          fema.get("RFLD_RISKS"),
            "flood_rating":         fema.get("RFLD_RISKR"),
            "earthquake_score":     fema.get("ERQK_RISKS"),
            "earthquake_rating":    fema.get("ERQK_RISKR"),
            "hurricane_score":      fema.get("HRCN_RISKS"),
            "hurricane_rating":     fema.get("HRCN_RISKR"),
            "tornado_score":        fema.get("TRND_RISKS"),
            "tornado_rating":       fema.get("TRND_RISKR"),
            "tsunami_score":        fema.get("TSUN_RISKS"),
            "tsunami_rating":       fema.get("TSUN_RISKR"),
            "landslide_score":      fema.get("LNDS_RISKS"),
            "landslide_rating":     fema.get("LNDS_RISKR"),
            "drought_score":        fema.get("DRGT_RISKS"),
            "drought_rating":       fema.get("DRGT_RISKR"),
            "heatwave_score":       fema.get("HWAV_RISKS"),
            "heatwave_rating":      fema.get("HWAV_RISKR"),
            "expected_annual_loss": fema.get("EAL_VALT"),
            "social_vulnerability": fema.get("SOVI_SCORE"),
            "community_resilience": fema.get("RESL_SCORE"),
            "raw_fema_data":        fema
        }

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# HEALTH CHECK: GET /
@app.get("/")
def root():
    return {"status": "ok", "service": "FEMA Risk API"}