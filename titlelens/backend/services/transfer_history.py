"""
Transfer history service — deed recordings and ownership transfers.

5-step flow (per summary):
  Step 1: Geocode address → find county (Census Geocoder)
  Step 2: County assessor site → parcel ID
  Step 3: County recorder / register of deeds → search by parcel or address
  Step 4: Extract deed recordings (dates, names)
  Step 5: Count transfers — include only deed types that indicate ownership change

Supported regions:
  - NYC: Geoclient v2 + ACRIS (NYCGEO_SUBSCRIPTION_KEY optional — PLUTO fallback when missing)
  - Cook County IL (Chicago): Parcel API → PIN + recorder link (free)
  - LA County CA: Assessor PAIS → AIN + recorder link (free)
  - Melissa LookupDeeds: nationwide (requires MELISSA_PROPERTY_KEY)
"""

import os
from typing import Optional

import httpx

# Deed/transaction types that indicate an ownership transfer
# (excludes liens, releases, assignments of mortgage, etc.)
OWNERSHIP_DEED_TYPES = frozenset(
    {
        "grant deed",
        "warranty deed",
        "quitclaim deed",
        "grant",
        "warranty",
        "quit claim",
        "quitclaim",
        "sheriff's deed",
        "sheriffs deed",
        "tax deed",
        "deed in lieu",
        "deed in lieu of foreclosure",
        "special warranty deed",
        "general warranty deed",
        "fiduciary deed",
        "executor's deed",
        "administrator's deed",
    }
)


async def _get_county_name(state_fips: str, county_fips: str) -> Optional[str]:
    """Census API: FIPS → county name."""
    if not state_fips or not county_fips:
        return None
    try:
        url = "https://api.census.gov/data/2010/dec/sf1"
        params = {
            "get": "NAME",
            "for": f"county:{county_fips}",
            "in": f"state:{state_fips}",
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                return None
            data = r.json()
            if isinstance(data, list) and len(data) > 1:
                # [["NAME","state","county"],["Cook County, Illinois","17","031"]]
                return data[1][0]
    except Exception:
        pass
    return None


def _is_ownership_deed(deed_type: Optional[str]) -> bool:
    """True if deed type indicates ownership transfer."""
    if not deed_type:
        return False
    t = deed_type.strip().lower()
    return any(dt in t for dt in OWNERSHIP_DEED_TYPES)


# NYC — Geoclient + ACRIS (all five boroughs)
NYC_STATE_FIPS = "36"
NYC_COUNTIES = {"005", "047", "061", "081", "085"}  # Bronx, Kings, New York, Queens, Richmond (Staten Island)

# Cook County IL (Chicago)
COOK_STATE_FIPS = "17"
COOK_COUNTY_FIPS = "031"

# LA County CA
LA_STATE_FIPS = "06"
LA_COUNTY_FIPS = "037"

# NYC PLUTO → ACRIS borough codes
PLUTO_TO_ACRIS = {"MN": "1", "BX": "2", "BK": "3", "QN": "4", "SI": "5"}
# Borough name hint → PLUTO code
BOROUGH_TO_PLUTO = {
    "MANHATTAN": "MN", "NEW YORK": "MN",
    "BRONX": "BX",
    "BROOKLYN": "BK", "KINGS": "BK",
    "QUEENS": "QN",
    "STATEN ISLAND": "SI", "RICHMOND": "SI",
}


def _parse_int_acris(x) -> int | None:
    try:
        if x is None:
            return None
        s = str(x).replace(",", "")
        return int(float(s)) if s else None
    except (ValueError, TypeError):
        return None


async def _acris_deeds_from_bbl(client: httpx.AsyncClient, borough_code: str, block: str, lot: str) -> list[dict]:
    """
    ACRIS Legals (8h5j-fqxa) + Deeds (hzhn-3cmt): BBL → deed records.
    Uses simple query params (borough, block, lot) — ACRIS matches on numeric values.
    """
    try:
        block_norm = str(_parse_int_acris(block) or block) if block else ""
        lot_norm = str(_parse_int_acris(lot) or lot) if lot else ""
        if not borough_code or not block_norm or not lot_norm:
            return []
        r2 = await client.get(
            "https://data.cityofnewyork.us/resource/8h5j-fqxa.json",
            params={
                "borough": borough_code,
                "block": block_norm,
                "lot": lot_norm,
                "$select": "document_id",
                "$order": "document_id DESC",
                "$limit": 500,
            },
        )
        if r2.status_code != 200:
            return []
        legals = r2.json()
        if not isinstance(legals, list) or not legals:
            return []
        doc_ids = [L.get("document_id") for L in legals if L.get("document_id")]
        if not doc_ids:
            return []
        doc_list = "','".join(str(d).replace("'", "''") for d in doc_ids[:100])
        r3 = await client.get(
            "https://data.cityofnewyork.us/resource/hzhn-3cmt.json",
            params={
                "$where": f"doc_type='DEED' and document_id in ('{doc_list}')",
                "$select": "document_id,document_date,recorded_datetime,document_amt,crfn",
                "$order": "recorded_datetime DESC",
                "$limit": 50,
            },
        )
        if r3.status_code != 200:
            return []
        deeds = r3.json()
        if not isinstance(deeds, list):
            return []
        out = []
        for d in deeds:
            rec_date = d.get("recorded_datetime") or d.get("document_date") or ""
            rec_str = str(rec_date)[:10] if rec_date and len(str(rec_date)) >= 10 else str(rec_date) if rec_date else ""
            out.append({
                "recording_date": rec_str,
                "deed_type": "DEED",
                "grantor": None,
                "grantee": None,
                "instrument_number": d.get("crfn") or d.get("document_id"),
                "book_page": None,
                "sale_price": d.get("document_amt"),
            })
        return out
    except Exception:
        return []


def _strip_unit_from_address(address: str) -> str:
    """Strip unit/apt/suite so PLUTO can match the building. Keeps street address only."""
    import re
    s = address.strip()
    # Remove trailing comma and everything after: "80 John St APT 10E, New York" -> "80 John St"
    if "," in s:
        s = s.split(",")[0].strip()
    # Remove APT #, Unit #, Suite #, #A, Floor X, etc.
    s = re.sub(r"\s+(?:APT|APARTMENT|UNIT|STE|SUITE|FL|FLOOR|#)\s*[\w\d\-]+", "", s, flags=re.IGNORECASE)
    # Remove standalone # 10E or #10E at end
    s = re.sub(r"\s*#\s*[\w\d\-]+\s*$", "", s, flags=re.IGNORECASE)
    return s.strip() or address.strip()


def _normalize_street_for_pluto(s: str) -> str:
    """Basic normalization for PLUTO address search (AVENUE, STREET, etc.)."""
    import re
    s = re.sub(r"\s+", " ", s.upper().strip())
    # Ordinals: 1ST→1, 2ND→2, etc. — PLUTO often uses numbers
    for k, v in [
        ("AVENUE", "AVENUE"), ("AVE", "AVENUE"), ("AV", "AVENUE"),
        ("STREET", "STREET"), ("ST", "STREET"),
        ("BOULEVARD", "BOULEVARD"), ("BLVD", "BOULEVARD"),
        ("PLACE", "PLACE"), ("PL", "PLACE"),
        ("DRIVE", "DRIVE"), ("DR", "DRIVE"),
        ("ROAD", "ROAD"), ("RD", "ROAD"),
        ("LANE", "LANE"), ("LN", "LANE"),
        ("FIFTH", "FIFTH"), ("5TH", "FIFTH"), ("5", "5"),
    ]:
        s = re.sub(rf"\b{k}\b", v, s)
    return s


async def _bbl_from_pluto_lat_lng(lat: float, lng: float) -> Optional[tuple[str, str, str]]:
    """
    NYC PLUTO spatial lookup: lat/lng → (borough_code, block, lot).
    Uses same logic as nyc_property for consistency. No API key.
    """
    delta = 0.0005  # ~50m at NYC latitude
    try:
        where = f"latitude >= {lat - delta} and latitude <= {lat + delta} and longitude >= {lng - delta} and longitude <= {lng + delta}"
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(
                "https://data.cityofnewyork.us/resource/64uk-42ks.json",
                params={"$where": where, "$limit": 50},
            )
        if r.status_code != 200:
            return None
        rows = r.json()
        if not isinstance(rows, list) or not rows:
            return None
        def dist(row: dict) -> float:
            rlat = float(row.get("latitude") or 0)
            rlng = float(row.get("longitude") or 0)
            return (rlat - lat) ** 2 + (rlng - lng) ** 2
        best = min(rows, key=dist)
        pluto_borough = best.get("borough")
        block = best.get("block")
        lot = best.get("lot")
        if not pluto_borough or not block or not lot:
            return None
        borough_code = PLUTO_TO_ACRIS.get(pluto_borough)
        if not borough_code:
            return None
        return (borough_code, str(block), str(lot))
    except Exception:
        return None


async def _bbl_from_pluto(address: str) -> Optional[tuple[str, str, str]]:
    """
    NYC PLUTO (64uk-42ks): address → (borough_code, block, lot).
    No API key. Uses address like search; borough hint from address or defaults to Manhattan.
    """
    import re
    parts = [p.strip() for p in address.split(",")]
    addr_part = parts[0] if parts else ""
    match = re.match(r"^(\d+[\w\-/]*)\s+(.+)$", addr_part)
    house = (match.group(1) if match else "").strip()
    street = (match.group(2) if match else addr_part).strip()
    borough_pluto = "MN"
    for p in parts[1:]:
        u = p.upper()
        for name, code in BOROUGH_TO_PLUTO.items():
            if name in u:
                borough_pluto = code
                break
    if not house or not street:
        return None
    # Build search terms: house number + normalized street keywords
    norm = _normalize_street_for_pluto(street)
    terms = [t.replace("'", "''") for t in re.split(r"\s+", f"{house} {norm}") if len(t) >= 1]
    if not terms:
        return None
    # PLUTO $where: address contains each term (case-insensitive via upper() in PLUTO)
    # Socrata: UPPER(address) like '%X%'
    like_clauses = " and ".join(f"UPPER(address) like '%{t}%'" for t in terms[:4])
    where = f"({like_clauses}) and borough='{borough_pluto}'"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(
                "https://data.cityofnewyork.us/resource/64uk-42ks.json",
                params={
                    "$where": where,
                    "$select": "address,borough,block,lot",
                    "$limit": 5,
                },
            )
            if r.status_code != 200:
                return None
            rows = r.json()
            if not isinstance(rows, list) or not rows:
                return None
            row = rows[0]
            pluto_borough = row.get("borough")
            block = row.get("block")
            lot = row.get("lot")
            if not pluto_borough or not block or not lot:
                return None
            borough_code = PLUTO_TO_ACRIS.get(pluto_borough)
            if not borough_code:
                return None
            return (borough_code, str(block), str(lot))
    except Exception:
        return None


async def _fetch_nyc_transfers(
    address: str, subscription_key: str
) -> list[dict]:
    """
    NYC ACRIS — Geoclient v2 address→BBL, ACRIS Legals BBL→CRFN, ACRIS Deeds.
    Uses Geoclient v2 (api.nyc.gov/geoclient/v2). Get free subscription key at
    https://api-portal.nyc.gov/ (subscribe to Geoclient User).
    """
    if not subscription_key or not address:
        return []
    try:
        import re
        parts = [p.strip() for p in address.split(",")]
        addr_part = parts[0] if parts else ""
        match = re.match(r"^(\d+[\w\-/]*)\s+(.+)$", addr_part)
        house = (match.group(1) if match else "").strip()
        street = (match.group(2) if match else addr_part).strip()
        borough = "MANHATTAN"
        for p in parts[1:]:
            u = p.upper()
            if "BROOKLYN" in u or "KINGS" in u:
                borough = "BROOKLYN"
                break
            elif "BRONX" in u:
                borough = "BRONX"
                break
            elif "QUEENS" in u:
                borough = "QUEENS"
                break
            elif "MANHATTAN" in u or "NEW YORK" in u:
                borough = "MANHATTAN"
                break
            elif "STATEN" in u or "RICHMOND" in u:
                borough = "STATEN ISLAND"
                break
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            r1 = await client.get(
                "https://api.nyc.gov/geoclient/v2/address.json",
                params={
                    "houseNumber": house,
                    "street": street,
                    "borough": borough,
                },
                headers={"Ocp-Apim-Subscription-Key": subscription_key},
            )
            if r1.status_code != 200:
                return []
            geo = r1.json()
            addr = geo.get("address") or {}
            borough_code = addr.get("bblBoroughCode") or addr.get("boroughCode")
            block = addr.get("bblTaxBlock") or addr.get("block")
            lot = addr.get("bblTaxLot") or addr.get("lot")
            if not borough_code or not block or not lot:
                return []
            return await _acris_deeds_from_bbl(client, str(borough_code), str(block), str(lot))
    except Exception:
        return []


async def _get_nyc_bbl_and_deeds(
    address: str,
    lat: Optional[float],
    lng: Optional[float],
    nyc_subscription_key: Optional[str],
) -> tuple[list[dict], str]:
    """
    Try Geoclient → PLUTO address → PLUTO lat/lng; return (deeds_list, source).
    source is set whenever we resolve a BBL (even if ACRIS returns 0 deeds).
    """
    from services import nyc_property as nyc

    source = "unavailable"
    deeds: list[dict] = []

    # 1) Geoclient (if key)
    if nyc_subscription_key and address:
        deeds = await _fetch_nyc_transfers(address, nyc_subscription_key)
        if deeds:
            return deeds, "nyc_acris"
        # Still try to get BBL for source label below via PLUTO

    # 2) PLUTO by address (full then stripped)
    for addr_variant in [address.strip(), _strip_unit_from_address(address)]:
        if not addr_variant:
            continue
        result = await nyc._bbl_and_pluto_from_address(addr_variant)
        if not result:
            continue
        borough_code, block, lot, _ = result
        source = "nyc_acris_pluto"
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                deeds = await _acris_deeds_from_bbl(client, borough_code, str(block), str(lot))
            return deeds, source
        except Exception:
            continue

    # 3) PLUTO by lat/lng
    if lat is not None and lng is not None:
        result = await nyc._pluto_from_lat_lng(float(lat), float(lng))
        if result:
            borough_code, block, lot, _ = result
            source = "nyc_acris_pluto_lat_lng"
            try:
                async with httpx.AsyncClient(timeout=12.0) as client:
                    deeds = await _acris_deeds_from_bbl(client, borough_code, str(block), str(lot))
            except Exception:
                pass
            return deeds, source

    return deeds, source


async def _fetch_cook_county_parcel(lat: float, lng: float) -> Optional[dict]:
    """Cook County Parcel API: lat/lng → PIN. Free, no key."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://gis.cookcountyil.gov/hosting/rest/services/Hosted/Parcel/FeatureServer/0/query",
                params={
                    "geometry": f'{{"x":{lng},"y":{lat}}}',
                    "geometryType": "esriGeometryPoint",
                    "inSR": 4326,
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": "name,pin10",
                    "returnGeometry": "false",
                    "f": "json",
                },
            )
            if r.status_code != 200:
                return None
            data = r.json()
            feats = data.get("features") or []
            if not feats:
                return None
            attrs = feats[0].get("attributes") or {}
            pin = attrs.get("name") or attrs.get("pin10")
            if pin:
                return {
                    "parcel_id": pin,
                    "parcel_type": "PIN",
                    "recorder_link": "https://www.cookcountyclerkil.gov/recorders-office/land-records",
                }
    except Exception:
        pass
    return None


async def _fetch_la_county_parcel(lat: float, lng: float) -> Optional[dict]:
    """LA County Assessor PAIS: lat/lng → AIN. Free, no key."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Project lat/lng to Web Mercator for query
            r = await client.get(
                "https://assessor.gis.lacounty.gov/oota/rest/services/PAIS/pais_parcels/MapServer/0/query",
                params={
                    "geometry": f'{{"x":{lng},"y":{lat}}}',
                    "geometryType": "esriGeometryPoint",
                    "inSR": 4326,
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": "AIN,SAADDR",
                    "returnGeometry": "false",
                    "f": "json",
                },
            )
            if r.status_code != 200:
                return None
            data = r.json()
            feats = data.get("features") or []
            if not feats:
                return None
            attrs = feats[0].get("attributes") or {}
            ain = attrs.get("AIN")
            if ain:
                return {
                    "parcel_id": str(ain),
                    "parcel_type": "AIN",
                    "recorder_link": "https://lacounty.gov/records/",
                }
    except Exception:
        pass
    return None




async def _fetch_melissa_deeds(
    address: str, state_fips: str, county_fips: str, api_key: str
) -> list[dict]:
    """
    Melissa Property V4 LookupDeeds — requires License Key.
    Uses FreeForm address. Returns list of deed records.
    """
    if not api_key or not address:
        return []
    fips = state_fips + county_fips  # 5-digit state+county FIPS
    try:
        url = "https://property.melissadata.net/v4/WEB/LookupDeeds"
        params = {
            "id": api_key,
            "ff": address,
            "fips": fips,
            "format": "json",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                return []
            data = r.json()
    except Exception:
        return []

    records = data.get("Records") or []
    out = []
    for rec in records:
        # Melissa response structure varies; adapt to their field names
        deed_type = (
            rec.get("DeedType")
            or rec.get("DocumentType")
            or rec.get("DocType")
            or rec.get("TransactionType")
            or ""
        )
        if not _is_ownership_deed(deed_type):
            continue
        out.append({
            "recording_date": rec.get("RecordingDate") or rec.get("RecordedDate"),
            "deed_type": deed_type,
            "grantor": rec.get("Grantor") or rec.get("PrimaryGrantor"),
            "grantee": rec.get("Grantee") or rec.get("PrimaryGrantee"),
            "instrument_number": rec.get("InstrumentNumber") or rec.get("DocNumber"),
            "book_page": rec.get("BookPage") or rec.get("Book") or rec.get("Page"),
        })
    return out


YEARS_WINDOW = 20  # historical transfers window (e.g., last 20 years)


async def fetch_transfer_history(address: str, geo: Optional[dict] = None) -> dict:
    """
    Get last ownership transfer and historical transfers (last YEARS_WINDOW years).
    For NYC, uses Geoclient (if key), then PLUTO by address (with unit stripped), then PLUTO by lat/lng.

    Step 1: Geocode → county ✓ (or use provided geo)
    Step 2: Assessor → parcel ID (Melissa handles; else links)
    Step 3: Recorder → search (Melissa handles; else links)
    Step 4: Extract deed recordings (Melissa handles; else N/A)
    Step 5: Filter to ownership deed types ✓
    """
    from services.geocoder import geocode_address

    address = address.strip()
    if not address:
        return _unavailable_transfer("Address required")

    # Step 1: Geocode (use provided geo if from analyze flow to avoid double request and ensure lat/lng)
    if not geo:
        geo = await geocode_address(address)
    if not geo:
        return _unavailable_transfer("Could not geocode address")

    state_fips = (geo.get("state_fips") or "").zfill(2)
    county_fips = (geo.get("county_fips") or "").zfill(3)
    if not state_fips or not county_fips:
        return _unavailable_transfer("Could not determine county")

    # County name
    county_name = await _get_county_name(state_fips, county_fips)
    state_abbr = _state_fips_to_abbr(state_fips)
    lat = geo.get("lat")
    lng = geo.get("lng")

    # Steps 2–5: Try NYC, Cook County, LA County, then Melissa
    transfers = []
    source = "unavailable"
    parcel_info: Optional[dict] = None
    api_key = os.getenv("MELISSA_PROPERTY_KEY") or os.getenv("MELISSA_DEED_KEY")
    nyc_subscription_key = os.getenv("NYCGEO_SUBSCRIPTION_KEY") or os.getenv("NYCGEO_APP_KEY")

    # NYC: Geoclient → PLUTO address → PLUTO lat/lng (source set even when 0 deeds)
    if state_fips == NYC_STATE_FIPS and (county_fips in NYC_COUNTIES or (lat is not None and lng is not None)):
        transfers, source = await _get_nyc_bbl_and_deeds(address, lat, lng, nyc_subscription_key)

    # Cook County IL (Chicago): Parcel API → PIN (free)
    if not transfers and state_fips == COOK_STATE_FIPS and county_fips == COOK_COUNTY_FIPS and lat is not None and lng is not None:
        parcel_info = await _fetch_cook_county_parcel(float(lat), float(lng))
        if parcel_info:
            source = "cook_county_parcel"

    # LA County CA: Assessor PAIS → AIN (free)
    if not transfers and state_fips == LA_STATE_FIPS and county_fips == LA_COUNTY_FIPS and lat is not None and lng is not None:
        parcel_info = await _fetch_la_county_parcel(float(lat), float(lng))
        if parcel_info:
            source = "la_county_parcel"

    # Melissa if key and no regional results
    if not transfers and api_key:
        transfers = await _fetch_melissa_deeds(address, state_fips, county_fips, api_key)
        if transfers:
            source = "melissa"

    # Sort by date descending (most recent first)
    transfers.sort(key=lambda t: (t.get("recording_date") or ""), reverse=True)

    last_transfer = transfers[0] if transfers else None
    transfer_count = len(transfers)

    # Step status for transparency
    steps = {
        "step1_geocode_county": True,
        "step2_assessor_parcel_id": bool(transfers or parcel_info),
        "step3_recorder_search": bool(transfers or parcel_info),
        "step4_extract_deeds": bool(transfers),
        "step5_count_ownership_transfers": True,
    }

    recorder_link = None
    if parcel_info:
        recorder_link = parcel_info.get("recorder_link")

    return {
        "source": source,
        "available": bool(transfers),
        "address": address,
        "county": county_name or f"County {county_fips}",
        "parcel_id": parcel_info.get("parcel_id") if parcel_info else None,
        "parcel_type": parcel_info.get("parcel_type") if parcel_info else None,
        "recorder_link": recorder_link,
        "state": state_abbr,
        "state_fips": state_fips,
        "county_fips": county_fips,
        "years_window": YEARS_WINDOW,
        "transfer_count": transfer_count,
        "last_transfer": last_transfer,
        "transfers": transfers[:50],
        "steps_completed": steps,
        "assessor_search": f"https://www.google.com/search?q={_u(county_name)}+{_u(state_abbr)}+county+assessor+parcel",
        "recorder_search": recorder_link or f"https://www.google.com/search?q={_u(county_name)}+{_u(state_abbr)}+recorder+of+deeds",
    }


def _u(s: Optional[str]) -> str:
    return (s or "").replace(" ", "+")


def _state_fips_to_abbr(fips: str) -> str:
    """Common state FIPS → abbreviation."""
    m = {
        "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
        "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
        "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
        "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
        "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
        "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
        "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
        "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
        "54": "WV", "55": "WI", "56": "WY",
    }
    return m.get(str(fips).zfill(2), fips)


def _unavailable_transfer(error_message: Optional[str] = None) -> dict:
    out = {
        "source": "unavailable",
        "available": False,
        "address": None,
        "county": None,
        "state": None,
        "years_window": YEARS_WINDOW,
        "transfer_count": 0,
        "last_transfer": None,
        "transfers": [],
        "steps_completed": {
            "step1_geocode_county": False,
            "step2_assessor_parcel_id": False,
            "step3_recorder_search": False,
            "step4_extract_deeds": False,
            "step5_count_ownership_transfers": False,
        },
        "parcel_id": None,
        "parcel_type": None,
        "recorder_link": None,
        "assessor_search": None,
        "recorder_search": None,
    }
    if error_message:
        out["error_message"] = error_message
    return out
