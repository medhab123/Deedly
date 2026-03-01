# TitleLens Scoring Field Reference

This document defines every value in the **confidence dashboard** produced by the scoring layer (`backend/services/scoring.py`). All values are computed deterministically from raw enrichment JSON — no ML model.

---

## Output Structure

The `compute_confidence_dashboard(raw)` function returns a dict with these top-level keys:

| Key | Description |
|-----|-------------|
| `ownership_confidence` | Overall title/ownership confidence label |
| `hidden_legal_risks` | Legal risks (HPD, DOB, misclassification, etc.) |
| `flood_risk` | FEMA NRI flood/climate risk |
| `crime_data` | Crime incident data quality and safety score |
| `co_status` | Certificate of occupancy retrieval status |
| `valuation_confidence` | Comparable sales and value estimate confidence |
| `misclassification_risk` | Property use classification mismatch risk |
| `insurance_risk` | Insurance risk (derived from flood/climate) |

---

## Field Definitions

### 1. Ownership Confidence

| Field | Values | Meaning |
|-------|--------|---------|
| `level` | `REVIEW RECOMMENDED` \| `SEE TRANSFER HISTORY` | Overall recommendation |
| `detail` | string | Human-readable explanation |

**Rules:**
- `REVIEW RECOMMENDED` if any hidden risk: misclassification suspected, CO not retrieved, Class 1 DOB, ECB violation, HPD count > 10, or open Class C violation
- `SEE TRANSFER HISTORY` otherwise

---

### 2. Hidden Legal Risks

| Field | Values | Meaning |
|-------|--------|---------|
| `level` | `VERY HIGH` \| `HIGH` \| `MODERATE` \| `NONE` | Severity |
| `detail` | string | Concise list of issues |

**Rules:**
- `VERY HIGH`: HPD count > 30, or Class 1 DOB violation, or open Class C violation
- `HIGH`: HPD count > 10, or 2+ hidden risk items
- `MODERATE`: 1 hidden risk item
- `NONE`: No hidden risks

**Sources:** `hpd.violation_count`, `nyc_property.hpd_violation_count`, `nyc_property.has_class1_dob`, `nyc_property.has_ecb_violations`, `nyc_property.misclassification.misclassification_suspected`, `nyc_property.co_status`, HPD violations with `class == "C"` and `status` containing `NOV SENT OUT` or `OPEN` or `PENDING`

---

### 3. Flood Risk

| Field | Values | Meaning |
|-------|--------|---------|
| `level` | `VERY HIGH` \| `HIGH` \| `MODERATE` \| `LOW` \| `UNKNOWN` | Risk level |
| `detail` | string | e.g. `VERY HIGH (98.3/100)` |
| `score` | float or null | FEMA NRI flood score (0–100) |
| `rating` | string or null | FEMA NRI text rating |

**Rules:**
- `VERY HIGH`: score ≥ 90
- `HIGH`: score ≥ 70
- `MODERATE`: score ≥ 40
- `LOW`: score < 40
- `UNKNOWN`: no score; fallback to `rating` text if available

**Sources:** `climate.flood_score`, `climate.flood_rating`, `climate.overall_score`, `climate.overall_rating` (FEMA NRI)

---

### 4. Crime Data

| Field | Values | Meaning |
|-------|--------|---------|
| `status` | `VERIFIED` \| `UNVERIFIED` \| `NOT AVAILABLE` | Data quality |
| `detail` | string | Explanation or incident count |
| `safety_score` | int 0–100 or null | Computed only when status = VERIFIED |
| `incident_count` | int or null | Incidents in ~1 mi, last 12 months |

**Rules:**
- `UNVERIFIED`: `crime.data_quality == "unverified"` — do not compute safety score; surface flag
- `VERIFIED`: incident count available; safety score derived: <50 → 85, <150 → 70, <400 → 55, else 40
- `NOT AVAILABLE`: No crime API for this area (e.g. state not supported)

**Sources:** `crime.incident_count`, `crime.data_quality`, `crime.data_quality_reason`

---

### 5. CO Status

| Field | Values | Meaning |
|-------|--------|---------|
| `status` | `RETRIEVED` \| `NOT RETRIEVED` | Certificate of occupancy |
| `detail` | string | Count or reason |

**Rules:**
- `RETRIEVED`: `nyc_property.co_status == "retrieved"`
- `NOT RETRIEVED`: CO not fetched for this BBL — misclassification check incomplete

**Sources:** `nyc_property.co_status`, `nyc_property.certificate_of_occupancy`

---

### 6. Valuation Confidence

| Field | Values | Meaning |
|-------|--------|---------|
| `level` | `HIGH` \| `MEDIUM` \| `LOW` | Confidence in value estimate |
| `detail` | string | e.g. `Est. $1,500,000 (12 comps)` or `No comps` |
| `comps_used` | int | Number of comparable sales used |
| `estimated_value` | int or null | Estimated value in USD |

**Rules:**
- `HIGH`: estimated value and comps ≥ 10
- `MEDIUM`: estimated value and comps ≥ 5
- `LOW`: comps < 5, or no comps

**Sources:** `nyc_property.valuation.comps_used`, `nyc_property.valuation.estimated_value`, `nyc_property.valuation.confidence`

---

### 7. Misclassification Risk

| Field | Values | Meaning |
|-------|--------|---------|
| `level` | `MODERATE` \| `LOW` \| `UNKNOWN` | Risk of use mismatch |
| `detail` | string | Flags (e.g. commercial units, CO unknown) |

**Rules:**
- `MODERATE`: `co_status == "not_retrieved"` AND `unitstotal != unitsres` — mixed-use but CO unknown; or `misclassification_suspected == true`
- `LOW`: No flags
- `UNKNOWN`: NYC property data not available

**Sources:** `nyc_property.pluto.unitstotal`, `nyc_property.pluto.unitsres`, `nyc_property.co_status`, `nyc_property.misclassification`

---

### 8. Insurance Risk

| Field | Values | Meaning |
|-------|--------|---------|
| `level` | `VERY HIGH` \| `HIGH` \| `MODERATE` \| `LOW` \| `UNKNOWN` | Derived from flood |
| `detail` | string | e.g. `VERY HIGH (flood score 98.3)` |

**Rules:** Same as flood risk — derived from FEMA NRI flood score/rating.

**Sources:** `climate.flood_score`, `climate.flood_rating`, `climate.overall_rating`

---

## Raw Input Fields Used

| Source | Key Paths |
|--------|-----------|
| `climate` | `flood_score`, `flood_rating`, `overall_score`, `overall_rating` |
| `crime` | `incident_count`, `data_quality`, `data_quality_reason` |
| `nyc_property` | `available`, `co_status`, `certificate_of_occupancy`, `hpd_violation_count`, `hpd_violations`, `has_class1_dob`, `has_ecb_violations`, `valuation`, `pluto`, `misclassification` |
| `hpd` | `violation_count`, `violations` (each: `class`, `status`) |

---

## Example Dashboard Output

```
Ownership Confidence:     REVIEW RECOMMENDED
Hidden Legal Risks:       HIGH (34 HPD violations, open Class C)
Flood Risk:               VERY HIGH (98.3/100)
Crime Data:               UNVERIFIED (flag)
CO Status:                NOT RETRIEVED (flag)
Valuation Confidence:     LOW (no comps)
Misclassification Risk:   MODERATE (4 commercial units, CO unknown)
Insurance Risk:           VERY HIGH
```
