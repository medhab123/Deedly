"""
Neighborhood Demographics — U.S. Census ACS 5-Year Estimates.
Uses real Census Bureau data: residency duration, move-in years, median income, race/ethnicity.

Data source: https://api.census.gov/data/2022/acs/acs5
No API key required for up to 500 requests/day.
"""

from typing import Optional

import httpx

CENSUS_BASE = "https://api.census.gov/data/2022/acs/acs5"

# ACS variable codes → friendly names
# Reference: https://api.census.gov/data/2022/acs/acs5/variables.html
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
    # Median year householder moved in
    "B25035_001E": "median_year_householder_moved_in",
}


def _parse_int(val) -> Optional[int]:
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _years_since(year: Optional[int]) -> Optional[int]:
    if year is None:
        return None
    return 2022 - year


def _build_move_in_breakdown(data: dict, tenure: str) -> dict:
    prefix = f"{tenure}_moved_in"
    breakdown = {
        "2019_or_later": _parse_int(data.get(f"{prefix}_2019_or_later")),
        "2015_to_2018": _parse_int(data.get(f"{prefix}_2015_to_2018")),
        "2010_to_2014": _parse_int(data.get(f"{prefix}_2010_to_2014")),
        "2000_to_2009": _parse_int(data.get(f"{prefix}_2000_to_2009")),
        "1990_to_1999": _parse_int(data.get(f"{prefix}_1990_to_1999")),
        "1989_or_earlier": _parse_int(data.get(f"{prefix}_1989_or_earlier")),
    }
    total = _parse_int(data.get(f"{tenure}_occupied_total")) or 1
    breakdown_pct = {
        k: round(v / total * 100, 1) if v else None for k, v in breakdown.items()
    }
    return {"counts": breakdown, "percentages": breakdown_pct, "total": total}


def _format_response(friendly: dict, geo_label: str, geo_ids: dict) -> dict:
    total_pop = _parse_int(friendly.get("total_population")) or 1
    median_year = _parse_int(friendly.get("median_year_householder_moved_in"))

    # Race breakdown
    race = {
        "white_alone": _parse_int(friendly.get("white_alone")),
        "black_or_african_american": _parse_int(
            friendly.get("black_or_african_american_alone")
        ),
        "asian": _parse_int(friendly.get("asian_alone")),
        "american_indian_alaska_native": _parse_int(
            friendly.get("american_indian_alaska_native_alone")
        ),
        "native_hawaiian_pacific_islander": _parse_int(
            friendly.get("native_hawaiian_pacific_islander_alone")
        ),
        "some_other_race": _parse_int(friendly.get("some_other_race_alone")),
        "two_or_more_races": _parse_int(friendly.get("two_or_more_races")),
        "hispanic_or_latino": _parse_int(friendly.get("hispanic_or_latino")),
    }
    race_pct = {
        k: round(v / total_pop * 100, 1) if v else None for k, v in race.items()
    }

    return {
        "geography": {
            "label": geo_label,
            **geo_ids,
            "data_source": "U.S. Census Bureau ACS 5-Year Estimates (2022)",
            "source_url": "https://api.census.gov/data/2022/acs/acs5",
        },
        "residency_duration": {
            "median_year_moved_in": median_year,
            "estimated_median_years_at_residence": _years_since(median_year),
            "note": "Based on median year householder moved into current home (B25035_001E)",
        },
        "when_neighbors_moved_in": {
            "owners": _build_move_in_breakdown(friendly, "owner"),
            "renters": _build_move_in_breakdown(friendly, "renter"),
        },
        "income": {
            "median_household_income_usd": _parse_int(
                friendly.get("median_household_income")
            ),
            "note": "Median household income in the past 12 months (B19013_001E, inflation-adjusted to 2022 dollars)",
        },
        "race_ethnicity": {
            "total_population": total_pop,
            "counts": race,
            "percentages": race_pct,
            "note": "Race categories from B02001; Hispanic/Latino from B03003 (may overlap with race categories)",
        },
    }


async def _fetch_census(
    geo_params: dict,
    api_key: Optional[str] = None,
) -> tuple[dict, dict]:
    """Fetch Census ACS data. Returns (friendly, raw)."""
    var_list = ",".join(VARIABLES.keys())
    params = {"get": var_list, **geo_params}
    if api_key:
        params["key"] = api_key

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(CENSUS_BASE, params=params)

    if resp.status_code != 200:
        raise RuntimeError(f"Census API error {resp.status_code}: {resp.text}")

    rows = resp.json()
    headers = rows[0]
    values = rows[1] if len(rows) > 1 else []

    raw = dict(zip(headers, values)) if headers and values else {}

    friendly = {}
    for code, name in VARIABLES.items():
        friendly[name] = raw.get(code)

    return friendly, raw


# ─── Public API ──────────────────────────────────────────────────────────────


async def fetch_demographics_by_zip(
    zip_code: str,
    api_key: Optional[str] = None,
) -> dict:
    """
    Neighborhood demographics for a 5-digit U.S. ZIP (ZCTA).
    Returns residency duration, move-in breakdown, income, race/ethnicity.
    """
    if not zip_code or not str(zip_code).replace(" ", "").isdigit() or len(str(zip_code).replace(" ", "")) != 5:
        raise ValueError("zip_code must be a 5-digit number")
    zip_code = str(zip_code).replace(" ", "").zfill(5)

    geo_params = {"for": f"zip code tabulation area:{zip_code}"}
    friendly, _ = await _fetch_census(geo_params, api_key)
    return _format_response(
        friendly,
        geo_label=f"ZIP Code {zip_code}",
        geo_ids={"zip_code": zip_code},
    )


async def fetch_demographics_by_county(
    state_fips: str,
    county_fips: str,
    api_key: Optional[str] = None,
) -> dict:
    """
    Neighborhood demographics for a U.S. county.
    state_fips: 2-digit (e.g. '06' California, '36' New York)
    county_fips: 3-digit (e.g. '059' Orange County CA, '061' New York County)
    """
    state_fips = str(state_fips).zfill(2)
    county_fips = str(county_fips).zfill(3)
    geo_params = {
        "for": f"county:{county_fips}",
        "in": f"state:{state_fips}",
    }
    friendly, _ = await _fetch_census(geo_params, api_key)
    return _format_response(
        friendly,
        geo_label=f"County {county_fips}, State {state_fips}",
        geo_ids={"state_fips": state_fips, "county_fips": county_fips},
    )


async def fetch_demographics_by_state(
    state_fips: str,
    api_key: Optional[str] = None,
) -> dict:
    """Neighborhood demographics for a U.S. state."""
    state_fips = str(state_fips).zfill(2)
    geo_params = {"for": f"state:{state_fips}"}
    friendly, _ = await _fetch_census(geo_params, api_key)
    return _format_response(
        friendly,
        geo_label=f"State FIPS {state_fips}",
        geo_ids={"state_fips": state_fips},
    )


async def fetch_demographics_for_address(
    state_fips: str,
    county_fips: str,
    zip_code: Optional[str] = None,
    api_key: Optional[str] = None,
) -> dict:
    """
    Fetch neighborhood demographics for an address.
    Prefers ZIP (ZCTA) for neighborhood-level data when available;
    otherwise falls back to county.
    """
    if zip_code and str(zip_code).replace(" ", "").isdigit() and len(str(zip_code).replace(" ", "")) == 5:
        try:
            return await fetch_demographics_by_zip(
                str(zip_code).replace(" ", "").zfill(5), api_key
            )
        except Exception:
            pass  # fall through to county

    if state_fips and county_fips:
        return await fetch_demographics_by_county(
            state_fips, county_fips, api_key
        )

    raise ValueError("Need zip_code or (state_fips + county_fips) for demographics")
