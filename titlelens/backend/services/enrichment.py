"""
Data enrichment services — Census, Walk Score, Crime (city open data), Schools (NCES).
All metrics are driven by backend APIs. If an API or key is missing,
fields are marked as unavailable instead of being fabricated.
"""

import os
from datetime import datetime, timedelta
from typing import Optional

import httpx

from services.schools import fetch_nces_public_schools_near
from services.hpd import fetch_hpd_for_address
from services.nyc_property import fetch_nyc_property_report
from services.demographics import fetch_demographics_for_address


async def fetch_fema_risk(geoid: str) -> dict:
    """
    FEMA National Risk Index — uses OpenFEMA API.
    Geoid format: SSCCC (state + county FIPS).
    Falls back to "unavailable" if API fails.
    """
    if not geoid or len(geoid) < 5:
        return _unavailable_fema()
    try:
        url = "https://www.fema.gov/api/open/v2/NationalRiskIndex"
        params = {"stateFips": geoid[:2], "countyFips": geoid[2:5], "year": "2023"}
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params=params)
            if r.status_code == 200:
                data = r.json()
                records = data.get("NationalRiskIndex", [])
                if records:
                    r0 = records[0]
                    return {
                        "flood_risk": r0.get("naturalHazardRiskRating"),
                        "expected_loss": r0.get("expectedAnnualLoss"),
                        "risk_index": r0.get("naturalHazardRiskIndex"),
                        "source": "fema",
                    }
    except Exception:
        pass
    return _unavailable_fema()


def _unavailable_fema() -> dict:
    """Fallback when FEMA API unavailable (no fabricated values)."""
    return {
        "flood_risk": None,
        "expected_loss": None,
        "risk_index": None,
        "source": "unavailable",
    }


async def fetch_fema_nri(geoid: str) -> dict:
    """
    FEMA National Risk Index (ArcGIS) — tract-level climate/disaster risk.
    Geoid = 11-digit Census tract GEOID (state + county + tract).
    Returns wildfire, flood, earthquake, hurricane, tornado, etc. scores & ratings.
    Same API as environment.py risk-report endpoint.
    """
    if not geoid or len(geoid) < 11:
        return _unavailable_fema_nri("Missing or invalid tract GEOID")
    url = "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/National_Risk_Index_Census_Tracts/FeatureServer/0/query"
    params = {
        "where": f"TRACTFIPS='{geoid}'",
        "outFields": "*",
        "returnGeometry": "false",
        "f": "json",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                return _unavailable_fema_nri(f"FEMA NRI API HTTP {r.status_code}")
            data = r.json()
            if "error" in data:
                return _unavailable_fema_nri(str(data["error"]))
            features = data.get("features") or []
            if not features:
                return _unavailable_fema_nri(f"No FEMA NRI data for tract {geoid}")
            fema = features[0].get("attributes") or {}
            return {
                "source": "fema_nri",
                "available": True,
                "dataset_version": fema.get("NRI_VER"),
                "tract": geoid,
                "county": fema.get("COUNTY"),
                "state": fema.get("STATEABBRV"),
                "overall_score": fema.get("RISK_SCORE"),
                "overall_rating": fema.get("RISK_RATNG"),
                "wildfire_score": fema.get("WFIR_RISKS"),
                "wildfire_rating": fema.get("WFIR_RISKR"),
                "flood_score": fema.get("IFLD_RISKS"),
                "flood_rating": fema.get("IFLD_RISKR"),
                "coastal_flood_score": fema.get("CFLD_RISKS"),
                "coastal_flood_rating": fema.get("CFLD_RISKR"),
                "earthquake_score": fema.get("ERQK_RISKS"),
                "earthquake_rating": fema.get("ERQK_RISKR"),
                "hurricane_score": fema.get("HRCN_RISKS"),
                "hurricane_rating": fema.get("HRCN_RISKR"),
                "tornado_score": fema.get("TRND_RISKS"),
                "tornado_rating": fema.get("TRND_RISKR"),
                "tsunami_score": fema.get("TSUN_RISKS"),
                "tsunami_rating": fema.get("TSUN_RISKR"),
                "landslide_score": fema.get("LNDS_RISKS"),
                "landslide_rating": fema.get("LNDS_RISKR"),
                "drought_score": fema.get("DRGT_RISKS"),
                "drought_rating": fema.get("DRGT_RISKR"),
                "heatwave_score": fema.get("HWAV_RISKS"),
                "heatwave_rating": fema.get("HWAV_RISKR"),
                "expected_annual_loss": fema.get("EAL_VALT"),
                "social_vulnerability": fema.get("SOVI_SCORE"),
                "community_resilience": fema.get("RESL_SCORE"),
            }
    except Exception as e:
        return _unavailable_fema_nri(str(e))


def _unavailable_fema_nri(error_message: Optional[str] = None) -> dict:
    """Fallback when FEMA NRI unavailable."""
    out = {
        "source": "unavailable",
        "available": False,
        "dataset_version": None,
        "tract": None,
        "county": None,
        "state": None,
        "overall_score": None,
        "overall_rating": None,
        "wildfire_score": None,
        "wildfire_rating": None,
        "flood_score": None,
        "flood_rating": None,
        "coastal_flood_score": None,
        "coastal_flood_rating": None,
        "earthquake_score": None,
        "earthquake_rating": None,
        "hurricane_score": None,
        "hurricane_rating": None,
        "tornado_score": None,
        "tornado_rating": None,
        "tsunami_score": None,
        "tsunami_rating": None,
        "landslide_score": None,
        "landslide_rating": None,
        "drought_score": None,
        "drought_rating": None,
        "heatwave_score": None,
        "heatwave_rating": None,
        "expected_annual_loss": None,
        "social_vulnerability": None,
        "community_resilience": None,
    }
    if error_message:
        out["error_message"] = error_message
    return out


async def fetch_census_demographics(geoid: str, census_key: Optional[str]) -> dict:
    """
    Census API — income, population, housing by tract.
    geoid = 11-digit tract (state+county+tract).
    Requires CENSUS_API_KEY in .env — Census Bureau now requires keys for ACS data.
    """
    if not geoid or len(geoid) < 11:
        return _unavailable_census("Missing or invalid tract GEOID")
    base = "https://api.census.gov/data/2022/acs/acs5"
    core_params = {
        "get": "NAME,B19013_001E,B01003_001E,B25077_001E",
        "for": "tract:" + geoid[-6:],
        "in": f"state:{geoid[:2]} county:{geoid[2:5]}",
    }
    # Census API works without key for <500 req/day (same URL that works in browser)
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            r = await client.get(base, params=core_params)
            if r.status_code != 200:
                body = r.text[:200] if r.text else ""
                return _unavailable_census(
                    f"Census API HTTP {r.status_code}: {body}"
                )
            try:
                data = r.json()
            except Exception:
                body_preview = (r.text or "")[:300].replace("\n", " ")
                return _unavailable_census(
                    f"Census returned non-JSON. Body starts: {body_preview}"
                )
            if len(data) > 1:
                header = data[0]
                row = data[1]
                obj = dict(zip(header, row))

                def to_int(x: Optional[str]) -> Optional[int]:
                    if x is None:
                        return None
                    try:
                        return int(float(x))
                    except Exception:
                        return None

                median_household_income = to_int(obj.get("B19013_001E"))
                population = to_int(obj.get("B01003_001E"))
                median_home_value = to_int(obj.get("B25077_001E"))

                return {
                    "tract_name": obj.get("NAME"),
                    "median_household_income": median_household_income,
                    "population": population,
                    "median_home_value": median_home_value,
                    "state": obj.get("state"),
                    "county": obj.get("county"),
                    "tract": obj.get("tract"),
                    "median_income": median_household_income,
                    "source": "census",
                }
            return _unavailable_census("Census API returned empty or unexpected data")
    except Exception as e:
        return _unavailable_census(str(e))


def _unavailable_census(error_message: Optional[str] = None) -> dict:
    """Fallback when Census API unavailable (no fabricated values)."""
    out = {
        "tract_name": None,
        "median_household_income": None,
        "population": None,
        "median_home_value": None,
        "state": None,
        "county": None,
        "tract": None,
        "median_income": None,
        "source": "unavailable",
    }
    if error_message:
        out["error_message"] = error_message
    return out


async def fetch_walk_score(lat: float, lng: float, address: str, ws_key: Optional[str]) -> dict:
    """
    Walk Score API — returns Walk Score, Transit Score, Bike Score per official docs.
    https://www.walkscore.com/professional/api.php
    Uses lat, lon, address, wsapikey. Set transit=1 and bike=1 for all scores.
    """
    if not ws_key or lat is None or lng is None:
        return _unavailable_walk(
            msg="WALKSCORE_API_KEY not set in .env, or lat/lng missing" if not ws_key else "lat/lng required for Walk Score"
        )
    try:
        url = "https://api.walkscore.com/score"
        params = {
            "format": "json",
            "address": address,
            "lat": lat,
            "lon": lng,
            "transit": 1,
            "bike": 1,
            "wsapikey": ws_key,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                return _unavailable_walk(msg=f"Walk Score HTTP {r.status_code}")
            data = r.json()
            status = data.get("status")
            # status 1 = success; 2 = calculating; 30 = invalid lat/lng; 40 = invalid key; 41 = quota exceeded; 42 = IP blocked
            if status != 1:
                err_msgs = {
                    2: "Score being calculated, not yet available",
                    30: "Invalid latitude/longitude",
                    31: "Walk Score API internal error",
                    40: "Invalid API key (check WALKSCORE_API_KEY in .env)",
                    41: "Daily API quota exceeded",
                    42: "IP address blocked",
                }
                return _unavailable_walk(msg=err_msgs.get(status, f"Walk Score status {status}"), api_status=status)

            transit = data.get("transit") if isinstance(data.get("transit"), dict) else None
            bike = data.get("bike") if isinstance(data.get("bike"), dict) else None

            return {
                "source": "walkscore",
                "status": status,
                "walkscore": data.get("walkscore"),
                "description": data.get("description"),
                "updated": data.get("updated"),
                "logo_url": data.get("logo_url"),
                "more_info_icon": data.get("more_info_icon"),
                "more_info_link": data.get("more_info_link"),
                "ws_link": data.get("ws_link"),
                "help_link": data.get("help_link"),
                "snapped_lat": data.get("snapped_lat"),
                "snapped_lon": data.get("snapped_lon"),
                "transit": transit,
                "bike": bike,
                # Flat keys for backward compatibility
                "walk_score": data.get("walkscore"),
                "transit_score": transit.get("score") if transit else None,
                "bike_score": bike.get("score") if bike else None,
            }
    except Exception:
        pass
    return _unavailable_walk()


def _unavailable_walk(msg: Optional[str] = None, api_status: Optional[int] = None) -> dict:
    """Fallback when Walk Score API unavailable (no fabricated values)."""
    out = {
        "source": "unavailable",
        "status": api_status,
        "walkscore": None,
        "description": None,
        "updated": None,
        "logo_url": None,
        "more_info_icon": None,
        "more_info_link": None,
        "ws_link": None,
        "help_link": None,
        "snapped_lat": None,
        "snapped_lon": None,
        "transit": None,
        "bike": None,
        "walk_score": None,
        "transit_score": None,
        "bike_score": None,
    }
    if msg:
        out["error_message"] = msg
    return out


async def fetch_regrid_parcel(lat: Optional[float], lng: Optional[float]) -> dict:
    """
    Regrid parcel API — closest thing to title-like data.
    Uses REGRID_API_TOKEN from environment. If unavailable,
    returns structure marked as unavailable.
    """
    token = os.getenv("REGRID_API_TOKEN")
    if not token or lat is None or lng is None:
        return {
            "source": "regrid",
            "available": False,
            "ownership_confidence": "UNKNOWN",
            "hidden_legal_risks": "UNKNOWN – full title search required",
            "owner_name": None,
            "zoning": None,
            "raw": None,
        }

    url = "https://api.regrid.com/api/v2/parcels/point"
    params = {
        "lat": lat,
        "lon": lng,
        "limit": 1,
        "token": token,
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                raise RuntimeError(f"Regrid error {r.status_code}")
            data = r.json()
    except Exception:
        return {
            "source": "regrid",
            "available": False,
            "ownership_confidence": "UNKNOWN",
            "hidden_legal_risks": "UNKNOWN – full title search required",
            "owner_name": None,
            "zoning": None,
            "raw": None,
        }

    features = data.get("features") or []
    if not features:
        return {
            "source": "regrid",
            "available": False,
            "ownership_confidence": "UNKNOWN",
            "hidden_legal_risks": "UNKNOWN – full title search required",
            "owner_name": None,
            "zoning": None,
            "raw": None,
        }

    props = features[0].get("properties", {}) or {}
    # Field names vary by jurisdiction; expose raw props and a few common aliases.
    owner_name = props.get("owner") or props.get("owner_name") or props.get("ownernm") or props.get("Owner")
    zoning = props.get("zoning") or props.get("zone") or props.get("zoningdesc")

    return {
        "source": "regrid",
        "available": True,
        # We only know that a parcel match exists; real title search is still required.
        "ownership_confidence": "HIGH" if owner_name or props else "MEDIUM",
        "hidden_legal_risks": "UNKNOWN – full title search required",
        "owner_name": owner_name,
        "zoning": zoning,
        "raw": props,
    }


async def fetch_crime_data(lat: Optional[float], lng: Optional[float], state_fips: str) -> dict:
    """
    Crime data from city open data APIs (Socrata SODA, ArcGIS REST).
    Supported: Chicago (IL 17), Seattle (WA 53), NYC (NY 36), DC (11). Others return unavailable.
    Queries incidents within ~1 mile (1600m) of lat/lng, last 12 months only.
    Returns time_range and time_range_days so counts are comparable.
    """
    if lat is None or lng is None:
        return _unavailable_crime("lat/lng required for crime query")
    radius_m = 1600  # ~1 mile
    # Date filter: last 12 months so counts are comparable across locations
    end_dt = datetime.utcnow()
    start_dt = end_dt - timedelta(days=365)
    start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
    time_range_str = f"{start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}"
    try:
        # Chicago (Cook County: state 17) - data.cityofchicago.org
        if state_fips == "17":
            where_clause = f"within_circle(location,{lat},{lng},{radius_m}) and date >= '{start_iso}' and date <= '{end_iso}'"
            url = "https://data.cityofchicago.org/resource/crimes.json"
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                # Get actual count (date filter applied; not capped)
                count_r = await client.get(url, params={"$select": "count(*)", "$where": where_clause})
                if count_r.status_code != 200:
                    return _unavailable_crime(f"Chicago API HTTP {count_r.status_code}")
                count_data = count_r.json()
                incident_count = int(count_data[0]["count"]) if isinstance(count_data, list) and count_data else 0
                # Fetch sample for type breakdown
                fetch_r = await client.get(
                    url,
                    params={
                        "$where": where_clause,
                        "$select": "primary_type",
                        "$order": "date DESC",
                        "$limit": 500,
                    },
                )
                data = fetch_r.json() if fetch_r.status_code == 200 else []
                type_counts: dict[str, int] = {}
                for row in data if isinstance(data, list) else []:
                    t = (row.get("primary_type") or "OTHER")
                    type_counts[t] = type_counts.get(t, 0) + 1
                out = {
                    "source": "chicago_open_data",
                    "available": True,
                    "incident_count": incident_count,
                    "time_range": time_range_str,
                    "time_range_days": 365,
                    "radius_meters": radius_m,
                    "primary_types": dict(sorted(type_counts.items(), key=lambda x: -x[1])[:10]),
                    "sample_count": min(len(data) if isinstance(data, list) else 0, 10),
                }
                if incident_count == 0 and state_fips == "17":
                    out["data_quality"] = "unverified"
                    out["data_quality_reason"] = "Zero incidents in dense urban area may indicate query or data issue"
                return out
        # Seattle (state 53) — uses lat/lng bounding box via $query (SoQL)
        if state_fips == "53":
            delta = 0.02  # ~1.4 miles
            start_date = start_dt.strftime("%Y-%m-%d")
            base_query = f"latitude >= '{lat - delta}' AND latitude <= '{lat + delta}' AND longitude >= '{lng - delta}' AND longitude <= '{lng + delta}' AND offense_date >= '{start_date}'"
            url = "https://data.seattle.gov/resource/tazs-3rd5.json"
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                count_r = await client.get(url, params={"$query": f"SELECT count(*) WHERE {base_query}"})
                if count_r.status_code != 200:
                    return _unavailable_crime(f"Seattle API HTTP {count_r.status_code}")
                count_data = count_r.json()
                incident_count = int(count_data[0]["count"]) if isinstance(count_data, list) and count_data else 0
                fetch_r = await client.get(url, params={"$query": f"SELECT offense_category WHERE {base_query} LIMIT 500"})
                data = fetch_r.json() if fetch_r.status_code == 200 else []
                type_counts: dict[str, int] = {}
                for row in data if isinstance(data, list) else []:
                    t = (row.get("offense_category") or "OTHER")
                    type_counts[t] = type_counts.get(t, 0) + 1
                out = {
                    "source": "seattle_open_data",
                    "available": True,
                    "incident_count": incident_count,
                    "time_range": time_range_str,
                    "time_range_days": 365,
                    "radius_meters": 2200,
                    "primary_types": dict(sorted(type_counts.items(), key=lambda x: -x[1])[:10]),
                    "sample_count": min(len(data) if isinstance(data, list) else 0, 10),
                }
                if incident_count == 0 and state_fips == "53":
                    out["data_quality"] = "unverified"
                    out["data_quality_reason"] = "Zero incidents in dense urban area may indicate query or data issue"
                return out
        # NYC (state 36) — query BOTH historic and current YTD datasets, combine counts
        if state_fips == "36":
            delta = 0.02  # ~1.4 miles
            # Date format for Socrata: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
            start_date = start_dt.strftime("%Y-%m-%d")
            end_date = end_dt.strftime("%Y-%m-%d")
            where_clause = f"latitude between {lat - delta} and {lat + delta} and longitude between {lng - delta} and {lng + delta} and cmplnt_fr_dt >= '{start_date}' and cmplnt_fr_dt <= '{end_date}'"
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                # Historic (qgea-i56i) — may have data through 2024
                url_historic = "https://data.cityofnewyork.us/resource/qgea-i56i.json"
                # Current YTD (5uac-w243) — has recent year data
                url_current = "https://data.cityofnewyork.us/resource/5uac-w243.json"
                # Query current YTD first (has recent data); fallback to historic
                incident_count = 0
                all_data: list = []
                for url in (url_current, url_historic):
                    try:
                        count_r = await client.get(url, params={"$select": "count(*)", "$where": where_clause})
                        if count_r.status_code != 200:
                            continue
                        count_data = count_r.json()
                        n = int(count_data[0]["count"]) if isinstance(count_data, list) and count_data else 0
                        if n > 0:
                            incident_count = n
                            fetch_r = await client.get(
                                url, params={"$where": where_clause, "$select": "ofns_desc", "$order": "cmplnt_fr_dt DESC", "$limit": 500},
                            )
                            rows = fetch_r.json() if fetch_r.status_code == 200 else []
                            all_data = rows if isinstance(rows, list) else []
                            break  # Use first dataset with data
                    except Exception:
                        continue
                type_counts = {}
                for row in all_data[:500]:
                    t = (row.get("ofns_desc") or "OTHER")
                    type_counts[t] = type_counts.get(t, 0) + 1
                out = {
                    "source": "nyc_open_data",
                    "available": True,
                    "incident_count": incident_count,
                    "time_range": time_range_str,
                    "time_range_days": 365,
                    "radius_meters": 2200,
                    "primary_types": dict(sorted(type_counts.items(), key=lambda x: -x[1])[:10]),
                    "sample_count": min(len(all_data), 10),
                }
                if incident_count == 0:
                    out["data_quality"] = "unverified"
                    out["data_quality_reason"] = "Zero incidents in dense urban area may indicate query or data issue"
                return out
        # DC (state 11) — ArcGIS REST FeatureServer, LATITUDE/LONGITUDE where clause
        if state_fips == "11":
            delta = 0.02  # ~1.4 miles
            start_arc = start_dt.strftime("%Y-%m-%d 00:00:00")
            end_arc = end_dt.strftime("%Y-%m-%d 23:59:59")
            where_clause = f"LATITUDE >= {lat - delta} AND LATITUDE <= {lat + delta} AND LONGITUDE >= {lng - delta} AND LONGITUDE <= {lng + delta} AND REPORT_DAT >= timestamp '{start_arc}' AND REPORT_DAT <= timestamp '{end_arc}'"
            url = "https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/MPD/FeatureServer/7/query"
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                count_r = await client.get(
                    url,
                    params={"where": where_clause, "returnCountOnly": "true", "f": "json"},
                )
                if count_r.status_code != 200:
                    return _unavailable_crime(f"DC ArcGIS API HTTP {count_r.status_code}")
                count_data = count_r.json()
                incident_count = int(count_data.get("count", 0))
                fetch_r = await client.get(
                    url,
                    params={
                        "where": where_clause,
                        "outFields": "OFFENSE",
                        "returnGeometry": "false",
                        "resultRecordCount": 500,
                        "f": "json",
                    },
                )
                data = fetch_r.json() if fetch_r.status_code == 200 else {}
                features = data.get("features") or []
                type_counts: dict[str, int] = {}
                for feat in features:
                    attrs = feat.get("attributes") or {}
                    t = (attrs.get("OFFENSE") or "OTHER")
                    type_counts[t] = type_counts.get(t, 0) + 1
                out = {
                    "source": "dc_arcgis",
                    "available": True,
                    "incident_count": incident_count,
                    "time_range": time_range_str,
                    "time_range_days": 365,
                    "radius_meters": 2200,
                    "primary_types": dict(sorted(type_counts.items(), key=lambda x: -x[1])[:10]),
                    "sample_count": min(len(features), 10),
                }
                if incident_count == 0 and state_fips == "11":
                    out["data_quality"] = "unverified"
                    out["data_quality_reason"] = "Zero incidents in dense urban area may indicate query or data issue"
                return out
        return _unavailable_crime(f"No crime API for state FIPS {state_fips}")
    except Exception as e:
        return _unavailable_crime(str(e))


def _unavailable_crime(error_message: Optional[str] = None) -> dict:
    out = {
        "source": "unavailable",
        "available": False,
        "incident_count": None,
        "time_range": None,
        "time_range_days": None,
        "radius_meters": None,
        "primary_types": None,
        "sample_count": None,
    }
    if error_message:
        out["error_message"] = error_message
    return out


async def enrich_property(
    address: str,
    geo: Optional[dict],
    census_key: Optional[str] = None,
    walkscore_key: Optional[str] = None,
) -> dict:
    """
    Run all enrichment in parallel and combine into one object.
    """
    import asyncio

    lat = geo.get("lat") if geo else None
    lng = geo.get("lng") if geo else None
    geoid = geo.get("full_geoid", "") if geo else ""
    state_fips = (geo.get("state_fips") or "").zfill(2) if geo else ""
    county_fips = (geo.get("county_fips") or "").zfill(3) if geo else ""

    # Optional: schools near point (only when we have coords)
    async def _schools_or_empty():
        if lat is None or lng is None:
            return []
        try:
            return await fetch_nces_public_schools_near(lat, lng, radius_miles=2.0, limit=10)
        except Exception:
            return []

    # Neighborhood demographics (Census ACS by ZIP or county)
    async def _neighborhood_demographics():
        if not state_fips or not county_fips:
            return None
        try:
            return await fetch_demographics_for_address(
                state_fips, county_fips, zip_code=geo.get("zip_code") if geo else None,
                api_key=census_key,
            )
        except Exception:
            return None

    # Parallel fetches: Census, Walk Score, crime, climate (FEMA NRI), schools, HPD (NYC), NYC property (NYC), neighborhood demographics
    tasks = [
        fetch_census_demographics(geoid, census_key),
        fetch_walk_score(lat, lng, address, walkscore_key),
        fetch_crime_data(lat, lng, state_fips),
        fetch_fema_nri(geoid),
        _schools_or_empty(),
        fetch_hpd_for_address(address, state_fips, county_fips),
        fetch_nyc_property_report(address, state_fips, county_fips, lat=lat, lng=lng),
        _neighborhood_demographics(),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    census = results[0] if not isinstance(results[0], Exception) else _unavailable_census()
    walk = results[1] if not isinstance(results[1], Exception) else _unavailable_walk()
    crime = results[2] if not isinstance(results[2], Exception) else _unavailable_crime()
    climate = results[3] if not isinstance(results[3], Exception) else _unavailable_fema_nri()
    schools_list = results[4] if not isinstance(results[4], Exception) else []
    hpd = results[5] if not isinstance(results[5], Exception) else {"available": False, "violations": [], "complaints": [], "violation_count": 0, "complaint_count": 0}
    nyc_property = results[6] if not isinstance(results[6], Exception) else {"available": False}
    neighborhood_demographics = results[7] if not isinstance(results[7], Exception) else None

    return {
        "address": address,
        "geocoded": {
            "lat": lat,
            "lng": lng,
            "tract": geo.get("tract") if geo else None,
            "matched_address": geo.get("matched_address") if geo else None,
            "tract_geoid": geo.get("full_geoid") if geo else None,
        },
        "walkability": walk,
        "demographics": census,
        "crime": crime,
        "climate": climate,
        "schools": schools_list,
        "hpd": hpd,
        "nyc_property": nyc_property,
        "neighborhood_demographics": neighborhood_demographics,
    }
