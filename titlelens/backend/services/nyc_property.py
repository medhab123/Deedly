"""
NYC Property Intelligence — PLUTO, CO, DOB/HPD violations, tax class, zoning,
sales comps (Citywide Rolling Calendar Sales usep-8jbt), valuation.
Flow: Geocode → BBL from PLUTO → PLUTO/CO/Tax/DOB/HPD/ACRIS/Sales → compare & flag.
"""

import re
from datetime import date, timedelta
from typing import Any, Optional

import httpx

# NYC Open Data datasets
PLUTO_URL = "https://data.cityofnewyork.us/resource/64uk-42ks.json"
SALES_URL = "https://data.cityofnewyork.us/resource/usep-8jbt.json"


def _parse_int(x: Any) -> Optional[int]:
    try:
        if x is None:
            return None
        s = str(x).replace(",", "")
        return int(float(s)) if s else None
    except (ValueError, TypeError):
        return None


def _parse_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        s = str(x).replace(",", "")
        return float(s) if s else None
    except (ValueError, TypeError):
        return None


def _months_ago_iso(months: int) -> str:
    days = int(months * 30.4)
    d = date.today() - timedelta(days=days)
    return d.isoformat()

NYC_STATE_FIPS = "36"
NYC_COUNTIES = {"005", "047", "061", "081"}  # Bronx, Kings, New York, Queens

PLUTO_TO_ACRIS = {"MN": "1", "BX": "2", "BK": "3", "QN": "4", "SI": "5"}
BOROUGH_TO_PLUTO = {
    "MANHATTAN": "MN", "NEW YORK": "MN",
    "BRONX": "BX", "BROOKLYN": "BK", "KINGS": "BK",
    "QUEENS": "QN", "STATEN ISLAND": "SI", "RICHMOND": "SI",
}

# Building class prefixes: A=1-family, B=2-family, C=walk-up, D=elevator, etc.
# Tax class: 1=1-3 family, 2=multi-family/condo, 3=utility, 4=commercial
RESIDENTIAL_BLDG_PREFIXES = ("A", "B", "C", "D", "R", "S")
COMMERCIAL_BLDG_PREFIXES = ("E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "T", "U", "V", "W")


def _normalize_street(s: str) -> str:
    """Normalize street for PLUTO search. PLUTO uses: WEST not W, 13 not 13TH, STREET not ST."""
    s = re.sub(r"\s+", " ", s.upper().strip())
    # Directional prefixes — PLUTO uses full names
    for abbr, full in [
        (r"\bW\b", "WEST"), (r"\bE\b", "EAST"), (r"\bN\b", "NORTH"), (r"\bS\b", "SOUTH"),
    ]:
        s = re.sub(abbr, full, s)
    # Ordinals — PLUTO uses bare numbers: 13TH → 13, 5TH → 5
    s = re.sub(r"(\d+)(ST|ND|RD|TH)\b", r"\1", s)
    # Street type abbreviations
    for abbr, full in [
        ("AVE", "AVENUE"), ("AVE.", "AVENUE"), ("AV", "AVENUE"),
        ("ST", "STREET"), ("ST.", "STREET"),
        ("BLVD", "BOULEVARD"), ("RD", "ROAD"), ("DR", "DRIVE"),
        ("PL", "PLACE"), ("LN", "LANE"),
        ("PKWY", "PARKWAY"), ("PKY", "PARKWAY"),
    ]:
        s = re.sub(rf"\b{re.escape(abbr)}\b", full, s)
    return s


def _bbl_format(borough_code: str, block: str, lot: str) -> str:
    """10-digit BBL: 1 digit borough + 5 digit block + 4 digit lot."""
    return f"{borough_code}{str(block).zfill(5)}{str(lot).zfill(4)}"


async def _pluto_from_lat_lng(lat: float, lng: float) -> Optional[tuple[str, str, str, dict]]:
    """
    PLUTO spatial lookup: lat/lng → nearest parcel.
    Uses bounding box (~50m) around point; returns closest row by distance.
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
        # Pick closest by euclidean distance (deg ~ 85km at NYC, so 0.0001 ~ 8.5m)
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
        return (borough_code, str(block), str(lot), best)
    except Exception:
        return None


async def _bbl_and_pluto_from_address(address: str) -> Optional[tuple[str, str, str, dict]]:
    """
    Address → (borough_code, block, lot, pluto_row).
    Returns None if no match.
    """
    parts = [p.strip() for p in address.split(",")]
    addr_part = parts[0] if parts else ""
    match = re.match(r"^(\d+[\w\-/]*)\s+(.+)$", addr_part.strip())
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
    norm = _normalize_street(street)
    terms = [t.replace("'", "''") for t in re.split(r"\s+", f"{house} {norm}") if len(t) >= 1]
    if not terms:
        return None
    # House number must appear at start (avoid 147 matching "47")
    house_esc = terms[0]
    like_clauses = [f"(UPPER(address) like '{house_esc} %' or UPPER(address) like '{house_esc}-%')"]
    for t in terms[1:4]:
        if t.isdigit() and len(t) <= 2:
            like_clauses.append(f"(UPPER(address) like '% {t} %' or UPPER(address) like '% {t} STREET%')")
        else:
            like_clauses.append(f"UPPER(address) like '%{t}%'")
    where = f"({' and '.join(like_clauses)}) and borough='{borough_pluto}'"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(
                "https://data.cityofnewyork.us/resource/64uk-42ks.json",
                params={
                    "$where": where,
                    "$limit": 1,
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
        return (borough_code, str(block), str(lot), row)
    except Exception:
        return None


async def _fetch_dob_co(bbl: str) -> list[dict]:
    """DOB Certificate of Occupancy (bs8b-p36w)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://data.cityofnewyork.us/resource/bs8b-p36w.json",
                params={
                    "$where": f"bbl='{bbl.replace(chr(39), chr(39)+chr(39))}'",
                    "$select": "job_number,job_type,c_o_issue_date,bin_number,house_number,street_name,block,lot,issue_type",
                    "$order": "c_o_issue_date DESC",
                    "$limit": 10,
                },
            )
        if r.status_code != 200:
            return []
        rows = r.json()
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


async def _fetch_dob_violations(borough_code: str, block: str, lot: str) -> list[dict]:
    """DOB Open Violations (3h2n-5cm9). Flag Class 1, ECB."""
    try:
        boro_esc = str(borough_code).replace("'", "''")
        block_esc = str(block).replace("'", "''")
        lot_esc = str(lot).replace("'", "''")
        where = f"boro='{boro_esc}' and block='{block_esc}' and lot='{lot_esc}'"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://data.cityofnewyork.us/resource/3h2n-5cm9.json",
                params={
                    "$where": where,
                    "$select": "issue_date,violation_type_code,violation_category,violation_number,description",
                    "$order": "issue_date DESC",
                    "$limit": 50,
                },
            )
        if r.status_code != 200:
            return []
        rows = r.json()
        if not isinstance(rows, list):
            return []
        out = []
        for row in rows:
            vcat = (row.get("violation_category") or "").upper()
            vtype = (row.get("violation_type_code") or "").upper()
            is_ecb = "ECB" in vcat or "ECB" in (row.get("violation_number") or "")
            is_class1 = "CLASS 1" in vcat or "IMMEDIATELY HAZARDOUS" in vcat
            out.append({
                "issue_date": (row.get("issue_date") or "")[:8] if row.get("issue_date") else None,
                "violation_type": row.get("violation_type_code"),
                "violation_category": row.get("violation_category"),
                "violation_number": row.get("violation_number"),
                "description": row.get("description"),
                "is_ecb": is_ecb,
                "is_class1": is_class1,
            })
        return out
    except Exception:
        return []


async def _fetch_hpd_violations_by_bbl(borough_code: str, block: str, lot: str) -> list[dict]:
    """HPD Violations (wvxf-dwi5) by BBL."""
    try:
        # HPD uses boroid 1-5, block, lot
        where = f"boroid='{borough_code}' and block='{str(block).replace(chr(39), chr(39)+chr(39))}' and lot='{str(lot).replace(chr(39), chr(39)+chr(39))}'"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://data.cityofnewyork.us/resource/wvxf-dwi5.json",
                params={
                    "$where": where,
                    "$select": "class,novdescription,novissueddate,currentstatus,inspectiondate",
                    "$order": "novissueddate DESC",
                    "$limit": 50,
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
                "class": row.get("class"),
                "description": row.get("novdescription"),
                "issued_date": (row.get("novissueddate") or "")[:10] if row.get("novissueddate") else None,
                "status": row.get("currentstatus"),
                "inspection_date": (row.get("inspectiondate") or "")[:10] if row.get("inspectiondate") else None,
            })
        return out
    except Exception:
        return []


async def _fetch_zoning(bbl: str) -> Optional[dict]:
    """Zoning districts (fdkv-4t4z)."""
    try:
        bbl_esc = str(bbl).replace("'", "''")
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://data.cityofnewyork.us/resource/fdkv-4t4z.json",
                params={
                    "$where": f"bbl='{bbl_esc}'",
                    "$limit": 1,
                },
            )
        if r.status_code != 200:
            return None
        rows = r.json()
        if isinstance(rows, list) and rows:
            row = rows[0]
            return {
                "zoning_district_1": row.get("zoning_district_1"),
                "zoning_district_2": row.get("zoning_district_2"),
                "special_district_1": row.get("special_district_1"),
                "zoning_map_number": row.get("zoning_map_number"),
            }
        return None
    except Exception:
        return None


async def _fetch_acris_deeds(borough_code: str, block: str, lot: str) -> list[dict]:
    """
    ACRIS Legals (8h5j-fqxa) + Deeds (hzhn-3cmt): BBL → deed records.
    Uses simple query params (borough, block, lot) — ACRIS matches on numeric values.
    Normalizes block/lot to strip leading zeros (577, 24).
    """
    try:
        # ACRIS expects borough=1, block=577, lot=24 (no leading zeros)
        block_norm = str(_parse_int(block) or block) if block else ""
        lot_norm = str(_parse_int(lot) or lot) if lot else ""
        if not borough_code or not block_norm or not lot_norm:
            return []
        async with httpx.AsyncClient(timeout=12.0) as client:
            # Legals: use simple params (not $where) — Socrata filters directly
            r1 = await client.get(
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
            if r1.status_code != 200:
                return []
            legals = r1.json()
            if not isinstance(legals, list) or not legals:
                return []
            doc_ids = [L.get("document_id") for L in legals if L.get("document_id")]
            if not doc_ids:
                return []
            doc_list = "','".join(str(d).replace("'", "''") for d in doc_ids[:100])
            r2 = await client.get(
                "https://data.cityofnewyork.us/resource/hzhn-3cmt.json",
                params={
                    "$where": f"doc_type='DEED' and document_id in ('{doc_list}')",
                    "$select": "document_id,document_date,recorded_datetime,document_amt,crfn",
                    "$order": "recorded_datetime DESC",
                    "$limit": 50,
                },
            )
            if r2.status_code != 200:
                return []
            deeds = r2.json()
            if not isinstance(deeds, list):
                return []
            # Enrich deeds with grantor/grantee from ACRIS Parties (636b-3b5g)
            parties_by_doc: dict[str, dict[str, str | None]] = {}
            if doc_ids:
                doc_list_p = "','".join(str(d).replace("'", "''") for d in doc_ids[:100])
                r3 = await client.get(
                    "https://data.cityofnewyork.us/resource/636b-3b5g.json",
                    params={
                        "$where": f"document_id in ('{doc_list_p}')",
                        "$select": "document_id,party_type,name",
                        "$limit": 500,
                    },
                )
                if r3.status_code == 200:
                    parties_raw = r3.json()
                    parties_list = parties_raw if isinstance(parties_raw, list) else []
                    for doc_id in doc_ids:
                        doc_parties = [p for p in parties_list if str(p.get("document_id")) == str(doc_id)]
                        grantors = [p.get("name") for p in doc_parties if p.get("party_type") == "1" and p.get("name")]
                        grantees = [p.get("name") for p in doc_parties if p.get("party_type") == "2" and p.get("name")]
                        parties_by_doc[str(doc_id)] = {
                            "grantor": "; ".join(grantors[:3]) if grantors else None,
                            "grantee": "; ".join(grantees[:3]) if grantees else None,
                        }
            out = []
            for d in deeds:
                rec = str(d.get("recorded_datetime") or d.get("document_date") or "")
                doc_id = d.get("document_id")
                p = parties_by_doc.get(str(doc_id), {}) if doc_id else {}
                out.append({
                    "recording_date": rec[:10] if len(rec) >= 10 else rec,
                    "instrument_number": d.get("crfn") or d.get("document_id"),
                    "sale_price": _parse_int(d.get("document_amt")),
                    "grantor": p.get("grantor"),
                    "grantee": p.get("grantee"),
                })
            return out
    except Exception:
        return []


async def _fetch_sales_comps(
    borough_code: str, block: str, zipcode: Optional[str], months: int = 12, limit: int = 20
) -> list[dict]:
    """
    NYC Citywide Rolling Calendar Sales (usep-8jbt).
    Comps: same borough + block; fallback to borough + zipcode.
    Filters: sale_price > 10k, gross_square_feet > 200.
    """
    since = _months_ago_iso(months) + "T00:00:00.000"
    base_where = f"sale_date >= '{since}' AND sale_price > 10000 AND gross_square_feet > 200"
    try:
        # Attempt 1: borough + block
        where1 = f"{base_where} AND borough = '{borough_code}' AND block = '{block}'"
        params = {
            "$select": "borough,neighborhood,building_class_category,address,zip_code,block,lot,gross_square_feet,land_square_feet,year_built,total_units,residential_units,commercial_units,sale_price,sale_date",
            "$where": where1,
            "$order": "sale_date DESC",
            "$limit": limit,
        }
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(SALES_URL, params=params)
        if r.status_code != 200:
            return []
        comps = r.json()
        if not isinstance(comps, list):
            return []
        # Fallback: borough + zipcode if too few comps
        if len(comps) < 3 and zipcode:
            where2 = f"{base_where} AND borough = '{borough_code}' AND zip_code = '{zipcode}'"
            params["$where"] = where2
            params["$limit"] = limit
            async with httpx.AsyncClient(timeout=12.0) as client:
                r2 = await client.get(SALES_URL, params=params)
            if r2.status_code == 200 and isinstance(r2.json(), list):
                comps = r2.json()
        out = []
        for c in comps:
            sp = _parse_int(c.get("sale_price"))
            sqft = _parse_int(str(c.get("gross_square_feet", "")).replace(",", ""))
            ppsf = round(sp / sqft, 2) if sp and sqft and sqft > 0 else None
            out.append({
                "borough": c.get("borough"),
                "neighborhood": c.get("neighborhood"),
                "address": c.get("address"),
                "zip_code": c.get("zip_code"),
                "block": _parse_int(c.get("block")),
                "lot": _parse_int(c.get("lot")),
                "sale_date": (c.get("sale_date") or "")[:10] if c.get("sale_date") else None,
                "sale_price": sp,
                "gross_sqft": sqft,
                "price_per_sqft": ppsf,
                "building_class_category": c.get("building_class_category"),
                "building_class_at_sale": c.get("building_class_at_time_of") or c.get("building_class_at_time_of_sale"),
                "year_built": _parse_int(c.get("year_built")),
                "total_units": _parse_int(c.get("total_units")),
                "residential_units": _parse_int(c.get("residential_units")),
                "commercial_units": _parse_int(c.get("commercial_units")),
            })
        return out
    except Exception:
        return []


async def fetch_sales_comps_near(
    address: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    months: int = 24,
    limit: int = 40,
) -> list[dict]:
    """
    Fetch NYC sales comps for address or lat/lng. Expands radius (longer months, higher limit)
    so the graph has enough property nodes for network risk.
    """
    result = None
    if address:
        result = await _bbl_and_pluto_from_address(address.strip())
    if not result and lat is not None and lng is not None:
        result = await _pluto_from_lat_lng(float(lat), float(lng))
    if not result:
        return []
    borough_code, block, lot, pluto_row = result
    zipcode = pluto_row.get("zipcode")
    return await _fetch_sales_comps(borough_code, str(block), zipcode, months=months, limit=limit)


async def fetch_sales_comps_from_bbl(
    bbl: str,
    zipcode: str | None = None,
    months: int = 24,
    limit: int = 40,
) -> list[dict]:
    """
    Fetch NYC sales comps using BBL directly. Borough(1) + block(5) + lot(4).
    Used when payload already has nyc_property.bbl — bypasses address/lat lookup.
    """
    if not bbl or len(bbl) < 10:
        return []
    borough_code = bbl[0]
    block = bbl[1:6].lstrip("0") or bbl[1:6]
    return await _fetch_sales_comps(borough_code, block, zipcode, months=months, limit=limit)


def _estimate_valuation(pluto_row: dict, comps: list[dict]) -> dict:
    """Estimate value from median $/sqft of comps * subject building area."""
    ppsfs = [c.get("price_per_sqft") for c in comps if c.get("price_per_sqft")]
    if not ppsfs:
        return {
            "median_price_per_sqft": None,
            "estimated_value": None,
            "confidence": "low",
            "comps_used": 0,
            "valuation_gap": True,
            "valuation_gap_reason": "No comparable sales with valid price/sqft — verify value manually",
        }
    ppsfs_sorted = sorted(ppsf for ppsf in ppsfs if ppsf is not None)
    n = len(ppsfs_sorted)
    med_ppsf = ppsfs_sorted[n // 2] if n % 2 == 1 else (ppsfs_sorted[n // 2 - 1] + ppsfs_sorted[n // 2]) / 2
    bldg_area = _parse_int(str(pluto_row.get("bldgarea", "")).replace(",", ""))
    est_value = int(med_ppsf * bldg_area) if med_ppsf and bldg_area else None
    confidence = "high" if n >= 10 else "medium" if n >= 5 else "low"
    return {
        "median_price_per_sqft": round(med_ppsf, 2),
        "estimated_value": est_value,
        "confidence": confidence,
        "comps_used": n,
    }


async def _fetch_tax(boro: str, block: str, lot: str, bbl: str) -> Optional[dict]:
    """Property tax / assessment (8y4t-faws) — tax class, bldg_class, owner."""
    try:
        bbl_esc = str(bbl).replace("'", "''")
        where = f"parid='{bbl_esc}'"
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(
                "https://data.cityofnewyork.us/resource/8y4t-faws.json",
                params={
                    "$where": where,
                    "$limit": 1,
                },
            )
        if r.status_code != 200:
            return None
        rows = r.json()
        if not isinstance(rows, list) or not rows:
            return None
        row = rows[0]
        tax_class = row.get("curtaxclass") or row.get("tentaxclass") or row.get("pytaxclass")
        return {
            "tax_class": str(tax_class) if tax_class is not None else None,
            "bldg_class": row.get("bldg_class"),
            "owner": row.get("owner"),
            "zoning": row.get("zoning"),
            "assessed_total": row.get("curacttot") or row.get("tenacttot"),
            "market_total": row.get("curmkttot") or row.get("tenmkttot"),
            "year_built": row.get("yrbuilt"),
        }
    except Exception:
        return None


def _infer_use_from_bldg_class(bldg_class: str) -> str:
    """Infer residential vs commercial from building class code."""
    if not bldg_class or len(bldg_class) < 1:
        return "unknown"
    prefix = bldg_class[0].upper()
    if prefix in RESIDENTIAL_BLDG_PREFIXES:
        return "residential"
    if prefix in COMMERCIAL_BLDG_PREFIXES:
        return "commercial"
    return "mixed_or_other"


def _infer_use_from_tax_class(tax_class: str) -> str:
    """Tax class 1=1-3 family, 2=multi-family/condo, 3=utility, 4=commercial."""
    tc = str(tax_class).strip() if tax_class else ""
    if tc == "1":
        return "residential"
    if tc == "2":
        return "residential"
    if tc == "3":
        return "utility"
    if tc == "4":
        return "commercial"
    return "unknown"


def _infer_use_from_co_job_type(job_type: str) -> str:
    """CO job_type: A=alteration, N=new, etc. Use is often in CO text; simplistic here."""
    if not job_type:
        return "unknown"
    j = str(job_type).upper()
    if j.startswith("A"):
        return "alteration"
    if j.startswith("N"):
        return "new"
    return "other"


def _compute_misclassification_flags(
    pluto: dict,
    co_list: list[dict],
    tax: Optional[dict],
) -> dict[str, Any]:
    """
    Compare PLUTO building class, CO legal use, tax class.
    Flag mismatches for human review.
    """
    pluto_bldg = pluto.get("bldgclass") or ""
    pluto_use = _infer_use_from_bldg_class(pluto_bldg)
    tax_class = (tax.get("tax_class") or tax.get("curtaxclass") or tax.get("tentaxclass") or tax.get("pytaxclass")) if tax else None
    tax_use = _infer_use_from_tax_class(str(tax_class) if tax_class is not None else "")
    co_use = "unknown"
    if co_list:
        jt = co_list[0].get("job_type") or ""
        co_use = _infer_use_from_co_job_type(jt)
    tax_bldg = (tax.get("bldg_class") or "") if tax else ""
    tax_bldg_use = _infer_use_from_bldg_class(tax_bldg)
    flags = []
    if pluto_use != tax_use and tax_use != "unknown" and pluto_use != "unknown":
        flags.append(f"PLUTO use ({pluto_use}) differs from tax class use ({tax_use})")
    if pluto_bldg and tax_bldg and pluto_bldg != tax_bldg:
        flags.append(f"PLUTO bldg class ({pluto_bldg}) differs from tax bldg class ({tax_bldg})")
    if tax_class == "4" and pluto_use == "residential":
        flags.append("Tax Class 4 (commercial) but PLUTO suggests residential — potential misclassification")
    if tax_class == "1" and pluto_use == "commercial":
        flags.append("Tax Class 1 (1-3 family) but PLUTO suggests commercial — potential misclassification")
    return {
        "pluto_use": pluto_use,
        "tax_use": tax_use,
        "co_use": co_use,
        "flags": flags,
        "misclassification_suspected": len(flags) > 0,
    }


def _unavailable_nyc_property(addr: str, msg: str) -> dict:
    return {
        "available": False,
        "address": addr,
        "message": msg,
        "bbl": None,
        "pluto": None,
        "certificate_of_occupancy": [],
        "tax": None,
        "zoning": None,
        "dob_violations": [],
        "hpd_violations": [],
        "acris_deeds": [],
        "acris_deed_count": 0,
        "sales_comps": [],
        "sales_comp_count": 0,
        "valuation": {"median_price_per_sqft": None, "estimated_value": None, "confidence": "low", "comps_used": 0},
        "misclassification": None,
        "datasets": None,
    }


async def fetch_nyc_property_report(
    address: str,
    state_fips: str,
    county_fips: str,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> dict:
    """
    Full NYC property intelligence report for an address.
    Step 1: BBL from PLUTO
    Step 2: PLUTO (building class, zoning, units, floors, lot area, assessed value, year built)
    Step 3: DOB Certificate of Occupancy
    Step 4: Property tax (tax class)
    Step 5: Compare PLUTO / CO / tax → misclassification flags
    Step 6: Open DOB + HPD violations
    Step 7: Zoning
    Step 8: ACRIS deeds — optional, can be merged separately
    """
    if state_fips != NYC_STATE_FIPS or county_fips not in NYC_COUNTIES:
        return _unavailable_nyc_property(address, "NYC property report is only available for NYC addresses (Manhattan, Brooklyn, Bronx, Queens).")

    result = None
    if lat is not None and lng is not None:
        result = await _pluto_from_lat_lng(float(lat), float(lng))
    if not result:
        result = await _bbl_and_pluto_from_address(address)
    if not result:
        return _unavailable_nyc_property(address, "Could not find BBL for address in PLUTO.")

    borough_code, block, lot, pluto_row = result
    bbl = _bbl_format(borough_code, block, lot)
    pluto = {
        "address": pluto_row.get("address"),
        "bbl": str(bbl).split(".")[0] if bbl else None,
        "borough_code": borough_code,
        "block": str(block),
        "zipcode": pluto_row.get("zipcode"),
        "bldgclass": pluto_row.get("bldgclass"),
        "zonedist1": pluto_row.get("zonedist1"),
        "landuse": pluto_row.get("landuse"),
        "unitsres": pluto_row.get("unitsres"),
        "unitstotal": pluto_row.get("unitstotal"),
        "numfloors": pluto_row.get("numfloors"),
        "lotarea": pluto_row.get("lotarea"),
        "bldgarea": pluto_row.get("bldgarea"),
        "assesstot": pluto_row.get("assesstot"),
        "yearbuilt": pluto_row.get("yearbuilt"),
        "ownername": pluto_row.get("ownername"),
    }
    co_list = await _fetch_dob_co(bbl)
    tax = await _fetch_tax(borough_code, block, lot, bbl)
    zoning = await _fetch_zoning(bbl)
    dob_violations = await _fetch_dob_violations(borough_code, block, lot)
    hpd_violations = await _fetch_hpd_violations_by_bbl(borough_code, block, lot)
    acris_deeds = await _fetch_acris_deeds(borough_code, block, lot)
    zipcode = pluto_row.get("zipcode")
    sales_comps = await _fetch_sales_comps(borough_code, block, zipcode, months=12, limit=20)
    valuation = _estimate_valuation(pluto_row, sales_comps)
    misclassification = _compute_misclassification_flags(pluto_row, co_list, tax)
    co_out = []
    for c in co_list:
        co_out.append({
            "job_number": c.get("job_number"),
            "job_type": c.get("job_type"),
            "issue_date": (c.get("c_o_issue_date") or "")[:10] if c.get("c_o_issue_date") else None,
            "bin": c.get("bin_number"),
            "issue_type": c.get("issue_type"),
        })
    co_status = "retrieved" if co_out else "not_retrieved"
    return {
        "available": True,
        "address": address,
        "bbl": bbl,
        "pluto": pluto,
        "certificate_of_occupancy": co_out,
        "co_status": co_status,
        "tax": tax,
        "zoning": zoning,
        "dob_violations": dob_violations,
        "hpd_violations": hpd_violations,
        "dob_violation_count": len(dob_violations),
        "hpd_violation_count": len(hpd_violations),
        "has_class1_dob": any(v.get("is_class1") for v in dob_violations),
        "has_ecb_violations": any(v.get("is_ecb") for v in dob_violations),
        "acris_deeds": acris_deeds,
        "acris_deed_count": len(acris_deeds),
        "sales_comps": sales_comps,
        "sales_comp_count": len(sales_comps),
        "valuation": valuation,
        "misclassification": misclassification,
        "source": "nyc_open_data",
        "datasets": {
            "pluto": "64uk-42ks",
            "dob_co": "bs8b-p36w",
            "dob_violations": "3h2n-5cm9",
            "hpd_violations": "wvxf-dwi5",
            "zoning": "fdkv-4t4z",
            "tax": "8y4t-faws",
            "acris_legals": "8h5j-fqxa",
            "acris_deeds": "hzhn-3cmt",
            "acris_parties": "636b-3b5g",
            "sales": "usep-8jbt",
        },
    }
