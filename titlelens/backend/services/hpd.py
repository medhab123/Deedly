"""
NYC HPD (Housing Preservation and Development) — violations and complaints.
Uses NYC Open Data (data.cityofnewyork.us), no API key required.
Only applicable for NYC addresses (state 36, NYC counties).
"""

import re
import httpx

NYC_STATE_FIPS = "36"
NYC_COUNTIES = {"005", "047", "061", "081"}  # Bronx, Kings, New York, Queens


def _parse_address_for_hpd(address: str) -> tuple[str, str, str | None]:
    """Parse address into house number, street, and street_number for HPD search."""
    parts = [p.strip() for p in address.split(",")]
    addr_part = parts[0] if parts else ""
    match = re.match(r"^(\d+[\w\-/]*)\s+(.+)$", addr_part.strip())
    if match:
        house = match.group(1).strip()
        street = match.group(2).strip()
        # Extract street number (e.g. 13 from 13th, 147 from 147th) for exact match
        num_match = re.search(r"(\d+)(?:ST|ND|RD|TH)?\b", street.upper())
        street_num = num_match.group(1) if num_match else None
        return (house, street, street_num)
    return ("", addr_part.strip(), None)


def _normalize_street(s: str) -> str:
    """Normalize street for HPD search. Expand W→WEST, ordinals 13TH→13, ST→STREET."""
    s = re.sub(r"\s+", " ", s.upper().strip())
    # Directionals
    for pat, full in [(r"\bW\b", "WEST"), (r"\bE\b", "EAST"), (r"\bN\b", "NORTH"), (r"\bS\b", "SOUTH")]:
        s = re.sub(pat, full, s)
    # Ordinals
    s = re.sub(r"(\d+)(ST|ND|RD|TH)\b", r"\1", s)
    # Street types
    for abbr, full in [
        ("AVE", "AVENUE"), ("AVE.", "AVENUE"), ("AV", "AVENUE"),
        ("ST", "STREET"), ("ST.", "STREET"),
        ("BLVD", "BOULEVARD"), ("RD", "ROAD"), ("DR", "DRIVE"),
    ]:
        s = re.sub(rf"\b{re.escape(abbr)}\b", full, s)
    return s


async def fetch_hpd_violations(address: str) -> list[dict]:
    """
    HPD Violations for NYC address. NYC Open Data 24cj-meh5.
    Returns list of violations with class, description, date, status.
    Filters by house number (exact) and street number (avoids 147th when querying 13th).
    """
    house, street, street_num = _parse_address_for_hpd(address)
    if not house or not street:
        return []
    house_esc = str(house).replace("'", "''")
    norm = _normalize_street(street)
    try:
        # housenumber exact match; streetname must contain street number or street name
        street_clause = ""
        if street_num:
            num_esc = str(street_num).replace("'", "''")
            street_clause = f" and (upper(streetname) like '% {num_esc} %' or upper(streetname) like '% {num_esc}TH%' or upper(streetname) like '% {num_esc}ST%' or upper(streetname) like '% {num_esc}ND%' or upper(streetname) like '% {num_esc}RD%')"
        else:
            terms = [t for t in norm.split() if len(t) >= 2]
            if terms:
                street_esc = str(terms[0]).replace("'", "''")
                street_clause = f" and upper(streetname) like '%{street_esc}%'"
        where = f"housenumber='{house_esc}'" + street_clause
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(
                "https://data.cityofnewyork.us/resource/24cj-meh5.json",
                params={
                    "$where": where,
                    "$select": "housenumber,streetname,zip,class,novdescription,novissueddate,currentstatus",
                    "$order": "novissueddate DESC",
                    "$limit": 25,
                },
            )
        if r.status_code != 200:
            return []
        rows = r.json()
        if not isinstance(rows, list):
            return []
        out = []
        for row in rows:
            out.append({
                "house_number": row.get("housenumber"),
                "street_name": row.get("streetname"),
                "zip": row.get("zip"),
                "class": row.get("class"),
                "description": row.get("novdescription"),
                "issued_date": (row.get("novissueddate") or "")[:10] if row.get("novissueddate") else None,
                "status": row.get("currentstatus"),
            })
        return out
    except Exception:
        return []


async def fetch_hpd_complaints(address: str) -> list[dict]:
    """
    311 HPD Complaints for NYC address. NYC Open Data cewg-5fre.
    Returns list of complaints with type, descriptor, status, dates.
    Filters by exact address: incident_address must START with house number and
    contain street number as distinct token (avoids pulling 547 W 187 when querying 47 W 13th).
    """
    house, street, street_num = _parse_address_for_hpd(address)
    if not house or not street:
        return []
    house_esc = str(house).replace("'", "''")
    try:
        # Require incident_address to START with house number — avoids 547, 247, etc.
        start_clause = f"(upper(incident_address) like '{house_esc.upper()} %' or upper(incident_address) like '{house_esc.upper()}-%' or upper(incident_address) like '{house_esc.upper()} ')"
        # Require street number as distinct token when available — avoids matching wrong streets
        street_clause = ""
        if street_num:
            num_esc = str(street_num).replace("'", "''")
            street_clause = f" and (upper(incident_address) like '% {num_esc} %' or upper(incident_address) like '% {num_esc}TH%' or upper(incident_address) like '% {num_esc}ST%' or upper(incident_address) like '% {num_esc}ND%' or upper(incident_address) like '% {num_esc}RD%')"
        where = start_clause + street_clause
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(
                "https://data.cityofnewyork.us/resource/cewg-5fre.json",
                params={
                    "$where": where,
                    "$select": "incident_address,complaint_type,descriptor,status,created_date,closed_date,borough",
                    "$order": "created_date DESC",
                    "$limit": 25,
                },
            )
        if r.status_code != 200:
            return []
        rows = r.json()
        if not isinstance(rows, list):
            return []
        out = []
        for row in rows:
            out.append({
                "address": row.get("incident_address"),
                "complaint_type": row.get("complaint_type"),
                "descriptor": row.get("descriptor"),
                "status": row.get("status"),
                "created_date": (row.get("created_date") or "")[:10] if row.get("created_date") else None,
                "closed_date": (row.get("closed_date") or "")[:10] if row.get("closed_date") else None,
                "borough": row.get("borough"),
            })
        return out
    except Exception:
        return []


async def fetch_hpd_for_address(
    address: str, state_fips: str, county_fips: str
) -> dict:
    """
    HPD violations and complaints for NYC address. Returns combined response.
    For non-NYC addresses, returns unavailable.
    """
    if state_fips != NYC_STATE_FIPS or county_fips not in NYC_COUNTIES:
        return {
            "available": False,
            "source": "unavailable",
            "address": address,
            "violations": [],
            "complaints": [],
            "violation_count": 0,
            "complaint_count": 0,
            "message": "HPD data is only available for NYC addresses (Manhattan, Brooklyn, Bronx, Queens).",
        }
    violations = await fetch_hpd_violations(address)
    complaints = await fetch_hpd_complaints(address)
    return {
        "available": True,
        "source": "nyc_open_data",
        "address": address,
        "violations": violations,
        "complaints": complaints,
        "violation_count": len(violations),
        "complaint_count": len(complaints),
    }
