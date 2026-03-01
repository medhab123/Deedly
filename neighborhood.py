"""
Neighborhood Demographics API
==============================
Uses the U.S. Census Bureau American Community Survey (ACS) 5-Year Estimates
Real dataset: ACS 5-Year Data (2022) via Census Bureau API

Dataset URL: https://api.census.gov/data/2022/acs/acs5
Documentation: https://www.census.gov/data/developers/data-sets/acs-5year.html
Variables reference: https://api.census.gov/data/2022/acs/acs5/variables.html

No API key required for up to 500 requests/day.
Get a free key at: https://api.census.gov/data/key_signup.html

Install dependencies:
    pip install fastapi uvicorn httpx

Run:
    uvicorn neighborhood_demographics_api:app --reload
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import httpx
from typing import Optional

app = FastAPI(
    title="Neighborhood Demographics API",
    description="""
    Pulls **real** U.S. Census ACS 5-Year data to show neighborhood demographics:
    - How long residents have lived there (years at residence)
    - When they moved in
    - Median household income
    - Race/ethnicity breakdown

    **Data source:** U.S. Census Bureau ACS 5-Year Estimates (2022)
    https://api.census.gov/data/2022/acs/acs5
    """,
    version="1.0.0"
)

CENSUS_BASE = "https://api.census.gov/data/2022/acs/acs5"

# ACS variable codes we care about
# Full list: https://api.census.gov/data/2022/acs/acs5/variables.html
VARIABLES = {
    # Tenure by year householder moved in
    "B25038_002E": "owner_occupied_total",
    "B25038_003E": "owner_moved_in_2019_or_later",
    "B25038_004E": "owner_moved_in_2015_to_2018",
    "B25038_005E": "owner_moved_in_2010_to_2014",
    "B25038_006E": "owner_moved_in_2000_to_2009",
    "B25038_007E": "owner_moved_in_1990_to_1999",
    "B25038_008E": "owner_moved_in_1989_or_earlier",
    "B25038_009E": "renter_occupied_total",
    "B25038_010E": "renter_moved_in_2019_or_later",
    "B25038_011E": "renter_moved_in_2015_to_2018",
    "B25038_012E": "renter_moved_in_2010_to_2014",
    "B25038_013E": "renter_moved_in_2000_to_2009",
    "B25038_014E": "renter_moved_in_1990_to_1999",
    "B25038_015E": "renter_moved_in_1989_or_earlier",

    # Median household income
    "B19013_001E": "median_household_income",

    # Race (total population by race)
    "B02001_001E": "total_population",
    "B02001_002E": "white_alone",
    "B02001_003E": "black_or_african_american_alone",
    "B02001_004E": "american_indian_alaska_native_alone",
    "B02001_005E": "asian_alone",
    "B02001_006E": "native_hawaiian_pacific_islander_alone",
    "B02001_007E": "some_other_race_alone",
    "B02001_008E": "two_or_more_races",

    # Hispanic/Latino (separate from race in Census)
    "B03003_003E": "hispanic_or_latino",

    # Median years in residence (proxy via median age of householder by tenure)
    "B25035_001E": "median_year_householder_moved_in",
}


def parse_int(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def years_since(year: Optional[int]) -> Optional[int]:
    if year is None:
        return None
    return 2022 - year


def build_move_in_breakdown(data: dict, tenure: str) -> dict:
    prefix = f"{tenure}_moved_in"
    breakdown = {
        "2019_or_later": parse_int(data.get(f"{prefix}_2019_or_later")),
        "2015_to_2018": parse_int(data.get(f"{prefix}_2015_to_2018")),
        "2010_to_2014": parse_int(data.get(f"{prefix}_2010_to_2014")),
        "2000_to_2009": parse_int(data.get(f"{prefix}_2000_to_2009")),
        "1990_to_1999": parse_int(data.get(f"{prefix}_1990_to_1999")),
        "1989_or_earlier": parse_int(data.get(f"{prefix}_1989_or_earlier")),
    }
    total = parse_int(data.get(f"{tenure}_occupied_total")) or 1
    breakdown_pct = {k: round(v / total * 100, 1) if v else None for k, v in breakdown.items()}
    return {"counts": breakdown, "percentages": breakdown_pct, "total": total}


async def fetch_census(geo_params: dict, api_key: Optional[str] = None):
    var_list = ",".join(VARIABLES.keys())
    params = {"get": var_list, **geo_params}
    if api_key:
        params["key"] = api_key

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(CENSUS_BASE, params=params)

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Census API error: {resp.text}")

    rows = resp.json()
    headers = rows[0]
    values = rows[1]  # first (and usually only) data row

    raw = dict(zip(headers, values))

    # Remap Census variable codes → friendly names
    friendly = {}
    for code, name in VARIABLES.items():
        friendly[name] = raw.get(code)

    return friendly, raw


def format_response(friendly: dict, geo_label: str, geo_ids: dict):
    total_pop = parse_int(friendly.get("total_population")) or 1
    median_year = parse_int(friendly.get("median_year_householder_moved_in"))

    # Race breakdown
    race = {
        "white_alone": parse_int(friendly.get("white_alone")),
        "black_or_african_american": parse_int(friendly.get("black_or_african_american_alone")),
        "asian": parse_int(friendly.get("asian_alone")),
        "american_indian_alaska_native": parse_int(friendly.get("american_indian_alaska_native_alone")),
        "native_hawaiian_pacific_islander": parse_int(friendly.get("native_hawaiian_pacific_islander_alone")),
        "some_other_race": parse_int(friendly.get("some_other_race_alone")),
        "two_or_more_races": parse_int(friendly.get("two_or_more_races")),
        "hispanic_or_latino": parse_int(friendly.get("hispanic_or_latino")),
    }
    race_pct = {k: round(v / total_pop * 100, 1) if v else None for k, v in race.items()}

    return {
        "geography": {
            "label": geo_label,
            **geo_ids,
            "data_source": "U.S. Census Bureau ACS 5-Year Estimates (2022)",
            "source_url": "https://api.census.gov/data/2022/acs/acs5",
        },
        "residency_duration": {
            "median_year_moved_in": median_year,
            "estimated_median_years_at_residence": years_since(median_year),
            "note": "Based on median year householder moved into current home (B25035_001E)"
        },
        "when_neighbors_moved_in": {
            "owners": build_move_in_breakdown(friendly, "owner"),
            "renters": build_move_in_breakdown(friendly, "renter"),
        },
        "income": {
            "median_household_income_usd": parse_int(friendly.get("median_household_income")),
            "note": "Median household income in the past 12 months (B19013_001E, inflation-adjusted to 2022 dollars)"
        },
        "race_ethnicity": {
            "total_population": total_pop,
            "counts": race,
            "percentages": race_pct,
            "note": "Race categories from B02001; Hispanic/Latino from B03003 (may overlap with race categories)"
        }
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/", summary="API info")
def root():
    return {
        "name": "Neighborhood Demographics API",
        "data_source": "U.S. Census ACS 5-Year Estimates (2022)",
        "dataset_url": "https://api.census.gov/data/2022/acs/acs5",
        "variables_reference": "https://api.census.gov/data/2022/acs/acs5/variables.html",
        "endpoints": {
            "by_zip_code": "/demographics/zip/{zip_code}",
            "by_county": "/demographics/county?state_fips=06&county_fips=059",
            "by_state": "/demographics/state/{state_fips}",
        },
        "example_calls": [
            "/demographics/zip/92697",        # Irvine, CA (UCI area)
            "/demographics/zip/10001",        # New York, NY
            "/demographics/county?state_fips=06&county_fips=059",  # Orange County, CA
        ]
    }


@app.get(
    "/demographics/zip/{zip_code}",
    summary="Demographics by ZIP code",
    description="""
    Returns neighborhood demographics for a given U.S. ZIP code (ZCTA).

    **Real data from:** https://api.census.gov/data/2022/acs/acs5

    - Years neighbors have lived there (median year moved in)
    - Move-in year breakdown for owners vs renters
    - Median household income
    - Race/ethnicity breakdown
    """
)
async def demographics_by_zip(
    zip_code: str,
    api_key: Optional[str] = Query(None, description="Optional Census API key for higher rate limits")
):
    if not zip_code.isdigit() or len(zip_code) != 5:
        raise HTTPException(status_code=400, detail="zip_code must be a 5-digit number")

    geo_params = {"for": f"zip code tabulation area:{zip_code}"}
    friendly, _ = await fetch_census(geo_params, api_key)

    return format_response(
        friendly,
        geo_label=f"ZIP Code {zip_code}",
        geo_ids={"zip_code": zip_code}
    )


@app.get(
    "/demographics/county",
    summary="Demographics by county",
    description="""
    Returns neighborhood demographics for a U.S. county.

    Provide `state_fips` (2-digit) and `county_fips` (3-digit).

    Examples:
    - Orange County, CA: state_fips=06, county_fips=059
    - Cook County, IL:   state_fips=17, county_fips=031
    - King County, WA:   state_fips=53, county_fips=033

    FIPS codes: https://www.census.gov/library/reference/code-lists/ansi.html
    """
)
async def demographics_by_county(
    state_fips: str = Query(..., description="2-digit state FIPS code, e.g. '06' for California"),
    county_fips: str = Query(..., description="3-digit county FIPS code, e.g. '059' for Orange County"),
    api_key: Optional[str] = Query(None)
):
    geo_params = {
        "for": f"county:{county_fips}",
        "in": f"state:{state_fips}"
    }
    friendly, _ = await fetch_census(geo_params, api_key)

    return format_response(
        friendly,
        geo_label=f"County {county_fips}, State {state_fips}",
        geo_ids={"state_fips": state_fips, "county_fips": county_fips}
    )


@app.get(
    "/demographics/state/{state_fips}",
    summary="Demographics by state",
    description="""
    Returns statewide demographics.

    State FIPS codes: https://www.census.gov/library/reference/code-lists/ansi.html
    Examples: 06=California, 36=New York, 48=Texas, 12=Florida
    """
)
async def demographics_by_state(
    state_fips: str,
    api_key: Optional[str] = Query(None)
):
    geo_params = {"for": f"state:{state_fips}"}
    friendly, _ = await fetch_census(geo_params, api_key)

    return format_response(
        friendly,
        geo_label=f"State FIPS {state_fips}",
        geo_ids={"state_fips": state_fips}
    )


@app.get("/variables", summary="List all Census variables used")
def list_variables():
    return {
        "source": "ACS 5-Year 2022",
        "reference_url": "https://api.census.gov/data/2022/acs/acs5/variables.html",
        "variables_used": VARIABLES
    }