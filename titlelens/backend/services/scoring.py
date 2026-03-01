"""
TitleLens Scoring Layer — deterministic rules from raw enrichment JSON.
Produces a normalized confidence dashboard with human-readable labels and flags.

No ML model — pure rules. See SCORING_FIELD_REFERENCE.md for field definitions.
"""

from typing import Any, Optional


def _parse_int(x: Any) -> Optional[int]:
    try:
        if x is None:
            return None
        s = str(x).replace(",", "").strip()
        return int(float(s)) if s else None
    except (ValueError, TypeError):
        return None


def _parse_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        s = str(x).replace(",", "").strip()
        return float(s) if s else None
    except (ValueError, TypeError):
        return None


def _flood_risk_level(score: Optional[float], rating: Optional[str]) -> str:
    """Flood risk: VERY HIGH, HIGH, MODERATE, LOW, UNKNOWN."""
    s = _parse_float(score)
    if s is not None:
        if s >= 90:
            return "VERY HIGH"
        if s >= 70:
            return "HIGH"
        if s >= 40:
            return "MODERATE"
        return "LOW"
    r = (rating or "").upper()
    if "VERY" in r or "EXTREME" in r:
        return "VERY HIGH"
    if "HIGH" in r or "RELATIVELY" in r:
        return "HIGH"
    if "MODERATE" in r or "RELATIVE" in r:
        return "MODERATE"
    if "LOW" in r or "MINIMAL" in r:
        return "LOW"
    return "UNKNOWN"


def _insurance_risk_level(
    flood_score: Optional[float],
    flood_rating: Optional[str],
    overall_rating: Optional[str],
) -> str:
    """Insurance risk from flood/climate data."""
    return _flood_risk_level(flood_score, flood_rating or overall_rating)


def _has_open_critical_hpd_violation(hpd_violations: list, address_hpd_violations: list) -> tuple[bool, str]:
    """
    Check for open critical HPD violation: class C + status NOV SENT OUT (or similar open).
    Returns (has_critical, detail_string).
    """
    all_v = list(hpd_violations or []) + list(address_hpd_violations or [])
    for v in all_v:
        vclass = (v.get("class") or "").upper().strip()
        status = (v.get("status") or v.get("currentstatus") or "").upper()
        # Open critical: Class C and NOV SENT OUT (or similar open status)
        if vclass == "C" and ("NOV SENT OUT" in status or "OPEN" in status or "PENDING" in status):
            return True, f"Open Class C violation: {status}"
    return False, ""


def compute_confidence_dashboard(raw: dict) -> dict:
    """
    Take raw enrichment JSON and output a normalized confidence dashboard.
    Deterministic rules — no model.
    """
    climate = raw.get("climate") or {}
    crime = raw.get("crime") or {}
    nyc = raw.get("nyc_property") or {}
    hpd = raw.get("hpd") or {}

    flood_score = _parse_float(climate.get("flood_score") or climate.get("overall_score"))
    flood_rating = climate.get("flood_rating") or climate.get("overall_rating")
    overall_rating = climate.get("overall_rating")

    hpd_count = (hpd.get("violation_count") or 0) + (nyc.get("hpd_violation_count") or 0)
    hpd_violations = hpd.get("violations") or []
    nyc_hpd_violations = nyc.get("hpd_violations") or []
    has_open_critical, open_critical_detail = _has_open_critical_hpd_violation(
        hpd_violations, nyc_hpd_violations
    )

    # ─── Ownership Confidence ─────────────────────────────────────────────────
    hidden_risk_items = []
    if nyc.get("available") and nyc.get("misclassification", {}).get("misclassification_suspected"):
        hidden_risk_items.append("Potential property classification mismatch")
    if nyc.get("available") and nyc.get("co_status") == "not_retrieved":
        hidden_risk_items.append("CO not retrieved")
    if nyc.get("has_class1_dob"):
        hidden_risk_items.append("Class 1 DOB violation (immediately hazardous)")
    if nyc.get("has_ecb_violations"):
        hidden_risk_items.append("ECB violation on record")
    if hpd_count > 10:
        hidden_risk_items.append(f"{hpd_count} HPD violations")
    if has_open_critical:
        hidden_risk_items.append(open_critical_detail or "Open Class C violation")

    ownership_confidence = "REVIEW RECOMMENDED" if hidden_risk_items else "SEE TRANSFER HISTORY"

    # ─── Hidden Legal Risks ───────────────────────────────────────────────────
    if hidden_risk_items:
        if hpd_count > 30 or nyc.get("has_class1_dob") or has_open_critical:
            hidden_legal_level = "VERY HIGH"
        elif hpd_count > 10 or len(hidden_risk_items) >= 2:
            hidden_legal_level = "HIGH"
        else:
            hidden_legal_level = "MODERATE"
        hidden_legal_detail = "; ".join(hidden_risk_items)
    else:
        hidden_legal_level = "NONE"
        hidden_legal_detail = "None identified"

    # ─── Flood Risk ───────────────────────────────────────────────────────────
    flood_level = _flood_risk_level(flood_score, flood_rating)
    flood_detail = f"VERY HIGH ({flood_score:.1f}/100)" if flood_score and flood_score >= 90 else (
        f"{flood_level} ({flood_score:.1f}/100)" if flood_score is not None else flood_level
    )

    # ─── Crime Data ───────────────────────────────────────────────────────────
    crime_unverified = crime.get("data_quality") == "unverified"
    inc = crime.get("incident_count")
    if crime_unverified:
        crime_status = "UNVERIFIED"
        crime_detail = crime.get("data_quality_reason") or "Crime data quality unverified — zero incidents in dense area may indicate query or data issue"
        safety_score = None
    elif inc is not None and isinstance(inc, int):
        crime_status = "VERIFIED"
        crime_detail = f"{inc} incidents in last 12 months (radius ~1 mi)"
        if inc < 50:
            safety_score = 85
        elif inc < 150:
            safety_score = 70
        elif inc < 400:
            safety_score = 55
        else:
            safety_score = 40
    else:
        crime_status = "NOT AVAILABLE"
        crime_detail = "No crime API for this area"
        safety_score = None

    # ─── CO Status ────────────────────────────────────────────────────────────
    co_status = "NOT RETRIEVED"
    co_detail = "Certificate of occupancy not retrieved"
    if nyc.get("available"):
        cs = nyc.get("co_status", "")
        if cs == "retrieved":
            co_list = nyc.get("certificate_of_occupancy") or []
            co_status = "RETRIEVED"
            co_detail = f"{len(co_list)} CO(s) on file" if co_list else "Retrieved (no CO records)"
        else:
            co_status = "NOT RETRIEVED"
            co_detail = "CO not retrieved — misclassification check incomplete"

    # ─── Valuation Confidence ─────────────────────────────────────────────────
    val = nyc.get("valuation") or {}
    comps_used = val.get("comps_used", 0)
    est_val = val.get("estimated_value")
    confidence_raw = val.get("confidence", "low")
    if est_val and comps_used >= 5:
        val_level = "HIGH" if comps_used >= 10 else "MEDIUM"
        val_detail = f"Est. ${est_val:,} ({comps_used} comps)"
    elif comps_used > 0:
        val_level = "LOW"
        val_detail = f"Limited comps ({comps_used}) — verify value manually"
    else:
        val_level = "LOW"
        val_detail = "No comparable sales — verify value manually"

    # ─── Misclassification Risk ───────────────────────────────────────────────
    pluto = nyc.get("pluto") or {}
    units_total = _parse_int(pluto.get("unitstotal"))
    units_res = _parse_int(pluto.get("unitsres"))
    misclass = nyc.get("misclassification") or {}
    misclass_suspected = misclass.get("misclassification_suspected", False)

    if not nyc.get("available"):
        misclass_level = "UNKNOWN"
        misclass_detail = "NYC property data not available"
    elif misclass_suspected:
        commercial_units = (units_total or 0) - (units_res or 0) if (units_total is not None and units_res is not None) else None
        flags = misclass.get("flags") or []
        detail_parts = []
        if commercial_units and commercial_units > 0:
            detail_parts.append(f"{commercial_units} commercial units")
        if nyc.get("co_status") == "not_retrieved" and units_total is not None and units_res is not None and units_total != units_res:
            detail_parts.append("CO unknown, units mismatch")
        if flags:
            detail_parts.extend(flags[:2])
        misclass_level = "MODERATE" if (nyc.get("co_status") == "not_retrieved" and units_total != units_res) else "MODERATE"
        misclass_detail = "; ".join(detail_parts) if detail_parts else "Potential classification mismatch"
    else:
        misclass_level = "LOW"
        misclass_detail = "No misclassification flags"

    # ─── Insurance Risk ───────────────────────────────────────────────────────
    insurance_level = _insurance_risk_level(flood_score, flood_rating, overall_rating)
    insurance_detail = f"{insurance_level} (flood score {flood_score:.1f})" if flood_score is not None else insurance_level

    return {
        "ownership_confidence": {
            "level": ownership_confidence,
            "detail": "; ".join(hidden_risk_items) if hidden_risk_items else "No hidden risks identified",
        },
        "hidden_legal_risks": {
            "level": hidden_legal_level,
            "detail": hidden_legal_detail,
        },
        "flood_risk": {
            "level": flood_level,
            "detail": flood_detail,
            "score": flood_score,
            "rating": flood_rating,
        },
        "crime_data": {
            "status": crime_status,
            "detail": crime_detail,
            "safety_score": safety_score,
            "incident_count": inc,
        },
        "co_status": {
            "status": co_status,
            "detail": co_detail,
        },
        "valuation_confidence": {
            "level": val_level,
            "detail": val_detail,
            "comps_used": comps_used,
            "estimated_value": est_val,
        },
        "misclassification_risk": {
            "level": misclass_level,
            "detail": misclass_detail,
        },
        "insurance_risk": {
            "level": insurance_level,
            "detail": insurance_detail,
        },
    }


def compute_risk_score(dashboard: dict) -> dict:
    """
    Compute overall property risk score 0-100 from confidence dashboard.
    Higher score = higher risk. Returns score, level, and justification list.
    """
    hl = dashboard.get("hidden_legal_risks") or {}
    fl = dashboard.get("flood_risk") or {}
    cr = dashboard.get("crime_data") or {}
    co = dashboard.get("co_status") or {}
    vc = dashboard.get("valuation_confidence") or {}
    mc = dashboard.get("misclassification_risk") or {}
    ir = dashboard.get("insurance_risk") or {}

    justification: list[str] = []
    risk_points = 0
    max_points = 100

    # Hidden legal risks (0–30)
    hl_level = hl.get("level", "NONE")
    if hl_level == "VERY HIGH":
        risk_points += 30
        justification.append(f"+30: {hl.get('detail', 'Very high legal risks')}")
    elif hl_level == "HIGH":
        risk_points += 22
        justification.append(f"+22: {hl.get('detail', 'High legal risks')}")
    elif hl_level == "MODERATE":
        risk_points += 12
        justification.append(f"+12: {hl.get('detail', 'Moderate legal risks')}")

    # Flood risk (0–25)
    fl_level = fl.get("level", "UNKNOWN")
    fl_score = _parse_float(fl.get("score"))
    if fl_level == "VERY HIGH" or (fl_score is not None and fl_score >= 90):
        risk_points += 25
        justification.append(f"+25: Flood risk very high ({fl_score or 'N/A'}/100)")
    elif fl_level == "HIGH":
        risk_points += 18
        justification.append(f"+18: Flood risk high ({fl_score or 'N/A'}/100)")
    elif fl_level == "MODERATE":
        risk_points += 8
        justification.append(f"+8: Flood risk moderate")

    # Insurance risk (0–15) — if not already captured by flood
    ir_level = ir.get("level", "")
    if ir_level == "VERY HIGH" and fl_level != "VERY HIGH":
        risk_points += min(15, max_points - risk_points)
        justification.append(f"+15: Insurance risk very high")

    # Crime/safety (0–15)
    crime_status = cr.get("status", "")
    safety = cr.get("safety_score")
    inc = cr.get("incident_count")
    if crime_status == "UNVERIFIED":
        risk_points += 10
        justification.append("+10: Crime data unverified")
    elif safety is not None:
        if safety < 50:
            risk_points += 15
            justification.append(f"+15: Safety score low ({safety}/100, {inc or 0} incidents)")
        elif safety < 70:
            risk_points += 8
            justification.append(f"+8: Safety score moderate ({safety}/100)")

    # CO status (0–8)
    co_status = co.get("status", "NOT RETRIEVED")
    if co_status == "NOT RETRIEVED":
        risk_points += 6
        justification.append("+6: CO not retrieved — misclassification check incomplete")

    # Valuation (0–7)
    vc_level = vc.get("level", "LOW")
    if vc_level == "LOW" and vc.get("comps_used", 0) == 0:
        risk_points += 5
        justification.append("+5: No comparable sales — valuation uncertain")

    # Misclassification (0–5)
    mc_level = mc.get("level", "")
    if mc_level == "MODERATE":
        risk_points += 4
        justification.append(f"+4: {mc.get('detail', 'Misclassification risk')}")

    score = min(100, risk_points)
    if score == 0:
        justification.append("No significant risk factors identified.")

    if score >= 70:
        level = "VERY HIGH"
    elif score >= 50:
        level = "HIGH"
    elif score >= 25:
        level = "MODERATE"
    else:
        level = "LOW"

    return {
        "score": score,
        "level": level,
        "max_score": 100,
        "justification": justification,
    }


def format_dashboard_text(dashboard: dict) -> str:
    """Format confidence dashboard as human-readable lines (e.g. for docs or logs)."""
    oc = dashboard["ownership_confidence"]
    hl = dashboard["hidden_legal_risks"]
    fl = dashboard["flood_risk"]
    cr = dashboard["crime_data"]
    co = dashboard["co_status"]
    vc = dashboard["valuation_confidence"]
    mc = dashboard["misclassification_risk"]
    ir = dashboard["insurance_risk"]
    return (
        f"Ownership Confidence:     {oc['level']}\n"
        f"Hidden Legal Risks:       {hl['level']} ({hl['detail']})\n"
        f"Flood Risk:               {fl['detail']}\n"
        f"Crime Data:               {cr['status']} ({cr['detail']})\n"
        f"CO Status:                {co['status']} ({co['detail']})\n"
        f"Valuation Confidence:     {vc['level']} ({vc['detail']})\n"
        f"Misclassification Risk:   {mc['level']} ({mc['detail']})\n"
        f"Insurance Risk:           {ir['detail']}"
    )
