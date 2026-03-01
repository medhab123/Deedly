"""
Deedly — Buyer Confidence Platform
FastAPI backend: title-health risk + neighborhood enrichment + AI copilot
"""

import copy
import json
import os
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from dotenv import load_dotenv

# Load .env from backend directory
load_dotenv(Path(__file__).resolve().parent / ".env")

# In-memory analysis store for Deedly (hackathon demo)
_analysis_store: dict[str, dict] = {}

from services.geocoder import geocode_address
from services.enrichment import enrich_property, fetch_fema_nri
from services.ai_service import answer_question, generate_risk_summary
from services.transfer_history import fetch_transfer_history
from services.schools import fetch_nces_public_schools_near
from services.hpd import fetch_hpd_for_address
from services.nyc_property import fetch_nyc_property_report
from services.scoring import compute_confidence_dashboard, compute_risk_score
from services.ml_predictor import (
    predict_from_raw,
    train_from_rows as ml_train_from_rows,
    get_trained_targets,
)
from services.property_graph import get_graph
from services.nyc_property import fetch_sales_comps_near, fetch_sales_comps_from_bbl
from services.demographics import (
    fetch_demographics_by_zip,
    fetch_demographics_by_county,
    fetch_demographics_by_state,
    fetch_demographics_for_address,
)

app = FastAPI(title="Deedly API", description="Buyer Confidence Platform — title-health + neighborhood + AI copilot")


def _bootstrap_ml_training() -> None:
    """
    Bootstrap-train the ML predictor on demo + synthetic NYC-style rows so AI predictions
    work for NYC properties without requiring POST /api/ai/train.
    Uses risk_score as target; value_range [0,100] and tier_thresholds [35,60] for LOW/MED/HIGH.
    """
    demo_path = Path(__file__).resolve().parent / "demo_responses.json"
    if not demo_path.exists():
        return
    try:
        with open(demo_path, encoding="utf-8") as f:
            demos = json.load(f)
    except Exception:
        return
    rows = []
    # Add real demo rows
    for key, data in demos.items():
        if not isinstance(data, dict):
            continue
        raw = copy.deepcopy(data)
        dash = raw.get("confidence_dashboard") or {}
        risk = raw.get("risk_score") or {}
        score = risk.get("score") if isinstance(risk, dict) else (risk if isinstance(risk, (int, float)) else None)
        if score is None and dash:
            risk_calc = compute_risk_score(dash)
            score = risk_calc.get("score")
        if score is not None:
            raw["confidence_dashboard"] = dash
            raw["risk_score"] = {"score": score, "level": risk.get("level", "MODERATE")}
            rows.append({"payload": raw, "risk_score": score})
    # Synthetic NYC-style rows: vary crime, flood, legal, valuation for diversity
    base_nyc = demos.get("demo1") or (demos.get(list(demos.keys())[0]) if demos else {})
    if base_nyc and isinstance(base_nyc, dict):
        for inc, flood, misclass, co_ok, comps, trans in [
            (20, 15, False, True, 12, 1),
            (80, 30, False, True, 5, 2),
            (150, 50, True, False, 0, 0),
            (300, 70, True, False, 0, 6),
            (450, 85, True, False, 0, 10),
            (60, 25, False, True, 15, 0),
            (200, 45, True, False, 3, 4),
            (100, 35, True, True, 8, 3),
        ]:
            raw = copy.deepcopy(base_nyc)
            raw.setdefault("crime", {})["incident_count"] = inc
            raw.setdefault("climate", {})["flood_score"] = flood
            raw["transfer_count"] = trans
            raw["transfers"] = [{"recording_date": "2020-01-01"}] * min(trans, 15) if trans else []
            nyc = raw.setdefault("nyc_property", {})
            nyc["co_status"] = "retrieved" if co_ok else "not_retrieved"
            nyc["misclassification"] = {"misclassification_suspected": misclass}
            nyc["valuation"] = {"comps_used": comps, "estimated_value": 800000 if comps else None}
            dash = compute_confidence_dashboard(raw)
            raw["confidence_dashboard"] = dash
            risk_result = compute_risk_score(dash)
            score = risk_result.get("score", 50)
            raw["risk_score"] = risk_result
            rows.append({"payload": raw, "risk_score": score})
    if len(rows) < 2:
        return
    try:
        ml_train_from_rows(
            target_key="risk_score",
            rows=rows,
            value_range=[0.0, 100.0],
            tier_thresholds=[35.0, 60.0],
        )
    except Exception:
        pass


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _on_startup() -> None:
    """Bootstrap ML model at startup so AI predictions work for NYC without manual training."""
    _bootstrap_ml_training()


class AnalyzeRequest(BaseModel):
    address: str


class ChatRequest(BaseModel):
    address: str
    question: str
    enrichment: dict | None = None


class DeedlyAnalyzeRequest(BaseModel):
    address: str
    persona: str = "Family"  # Family, Investor, First-time buyer, Remote worker


class DeedlyAskRequest(BaseModel):
    analysisId: str
    question: str


class AIPredictRequest(BaseModel):
    """Request body for ML prediction: target (required), then analysisId or payload."""
    target: str
    analysisId: str | None = None
    payload: dict | None = None


class AITrainRequest(BaseModel):
    """Request body for ML training: target key and labeled rows (payload + label). No hardcoded data."""
    target: str
    rows: list[dict]  # each: { "payload": {...enrichment...}, "<target>": <number> } or nested path
    value_range: list[float] | None = None  # e.g. [0, 100] for clipping and optional tier
    tier_thresholds: list[float] | None = None  # e.g. [35, 60] -> LOW < 35, MED < 60, HIGH


class GraphRequest(BaseModel):
    """Request for graph ingest or predict: analysisId (from stored analysis) or payload (enrichment JSON)."""
    analysisId: str | None = None
    payload: dict | None = None


def _augment_for_frontend(e: dict) -> dict:
    """Add derived fields so frontend dashboard displays correctly. Uses scoring layer for consistency."""
    dash = compute_confidence_dashboard(e)
    e["confidence_dashboard"] = dash
    # Populate frontend fields from scoring output (single source of truth)
    e["title"] = {
        "ownership_confidence": dash["ownership_confidence"]["level"],
        "hidden_legal_risks": dash["hidden_legal_risks"]["detail"],
    }
    e["environmental"] = {
        "flood_risk": dash["flood_risk"]["detail"],
        "flood_score": dash["flood_risk"].get("score"),
        "flood_rating": dash["flood_risk"].get("rating"),
    }
    e["safety_score"] = dash["crime_data"].get("safety_score")
    val = dash["valuation_confidence"]
    e["value_trend"] = val["detail"]
    if val.get("comps_used", 0) == 0 and val.get("level") == "LOW":
        e["valuation_gap"] = True
    e["insurance_risk"] = dash["insurance_risk"]["detail"]
    # Risk score (0-100, higher = higher risk) with justification
    e["risk_score"] = compute_risk_score(dash)
    return e


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    """
    Analyze a property: geocode → enrich → transfer history (deed data) → AI summary.
    Returns combined property confidence data. NYC addresses always get transfer_history values.
    """
    address = req.address.strip()
    if not address:
        raise HTTPException(status_code=400, detail="Address required")

    geo = await geocode_address(address)
    enrichment = await enrich_property(
        address,
        geo,
        census_key=os.getenv("CENSUS_API_KEY"),
        walkscore_key=os.getenv("WALKSCORE_API_KEY"),
    )
    # Deed/transfer history (NYC: ACRIS with multiple BBL lookups so every address gets values)
    transfer = await fetch_transfer_history(address, geo=geo)
    enrichment["transfer_history"] = transfer
    enrichment["transfer_count"] = transfer.get("transfer_count", 0)
    enrichment["last_transfer"] = transfer.get("last_transfer")
    enrichment["transfers"] = transfer.get("transfers", [])[:50]
    enrichment["transfer_source"] = transfer.get("source", "unavailable")

    augmented = _augment_for_frontend(enrichment)
    # AI-generated property risk summary using all data
    augmented["risk_summary"] = await generate_risk_summary(augmented)
    augmented["ai_summary"] = augmented["risk_summary"]
    return augmented


def _to_deedly_response(augmented: dict, persona: str) -> dict:
    """Map augmented enrichment to Deedly API format."""
    risk = augmented.get("risk_score") or {}
    dash = augmented.get("confidence_dashboard") or {}
    crime = augmented.get("crime") or {}
    climate = augmented.get("climate") or {}
    nbhd = augmented.get("neighborhood_demographics") or augmented.get("demographics") or {}
    rs = risk.get("score", 0)
    level = (risk.get("level") or "MODERATE").upper()
    title_health_level = "LOW" if level in ("LOW",) else "MED" if level in ("MODERATE",) else "HIGH"
    flags = []
    if dash.get("hidden_legal_risks", {}).get("level") in ("HIGH", "VERY HIGH"):
        flags.append({"label": "Legal risks", "level": "high"})
    if dash.get("flood_risk", {}).get("level") in ("HIGH", "VERY HIGH"):
        flags.append({"label": "Flood zone", "level": "high"})
    transfer_count = augmented.get("transfer_count", 0)
    if transfer_count >= 5:
        flags.append({"label": "High turnover", "level": "med"})
    if dash.get("valuation_confidence", {}).get("comps_used", 0) == 0:
        flags.append({"label": "No comps", "level": "med"})
    if ((augmented.get("nyc_property") or {}).get("misclassification") or {}).get("misclassification_suspected"):
        flags.append({"label": "Easement found", "level": "med"})
    title_detail = dash.get("hidden_legal_risks") or {}
    nyc = augmented.get("nyc_property") or {}
    claim_likelihood = 3 if title_health_level == "LOW" else 8 if title_health_level == "MED" else 15
    title_health = {
        "level": title_health_level,
        "ownership_turnover": f"{transfer_count} transfers in 20 yrs",
        "liens": nyc.get("liens") or "None recorded",
        "easements": nyc.get("easements") or (title_detail.get("detail", "") or "Standard utility"),
        "zoning": (nyc.get("pluto") or {}).get("zonedist1") or "Residential",
        "claimLikelihood": claim_likelihood,
    }
    safety_score = augmented.get("safety_score")
    flood_score = climate.get("flood_score") or 0
    nbhd_stability = 70
    if nbhd and isinstance(nbhd, dict):
        inc = (nbhd.get("income") or {}).get("median_household_income_usd") if isinstance(nbhd.get("income"), dict) else nbhd.get("median_income")
        if inc and inc > 80000:
            nbhd_stability = 80
    scores = {
        "deedlyScore": rs,
        "safety": safety_score if safety_score is not None else 65,
        "titleHealth": 100 - min(100, rs),
        "environmental": 100 - min(100, flood_score or 0),
        "neighborhoodStability": nbhd_stability,
    }
    persona_insights = _persona_insights(persona, augmented)
    return {
        "property": {
            "address": augmented.get("address"),
            "geocoded": augmented.get("geocoded", {}),
            "lat": augmented.get("geocoded", {}).get("lat"),
            "lng": augmented.get("geocoded", {}).get("lng"),
        },
        "scores": scores,
        "titleHealth": title_health,
        "flags": flags,
        "personaInsights": persona_insights,
        "summary": augmented.get("ai_summary") or augmented.get("risk_summary") or "",
        "_raw": augmented,
    }


def _persona_insights(persona: str, aug: dict) -> dict:
    """Generate persona-specific insights from enrichment."""
    schools = aug.get("schools") or []
    crime = aug.get("crime") or {}
    climate = aug.get("climate") or {}
    walk = aug.get("walkability") or {}
    nbhd = aug.get("neighborhood_demographics") or aug.get("demographics") or {}
    pros = []
    watchouts = []
    if persona == "Family":
        pros.extend(["Schools within 2 mi" if schools else "Check schools", "Safety data available" if crime.get("available") else "Review crime data"])
        if climate.get("flood_rating") in ("LOW", "MINIMAL"):
            pros.append("Low flood risk")
        else:
            watchouts.append("Flood/climate risk present")
    elif persona == "Investor":
        tc = aug.get("transfer_count", 0)
        pros.append(f"{tc} deed transfers in 20 yrs" if tc else "Review transfer history")
        if aug.get("value_trend"):
            pros.append("Valuation data available")
        watchouts.append("Verify rent demand for area")
    elif persona == "First-time buyer":
        pros.append("Use AI copilot for questions")
        watchouts.extend(["Review top 3 risks", "Verify affordability"])
    else:
        pros.extend(["Walk score: " + str(walk.get("walk_score") or "—"), "Transit: " + str(walk.get("transit_score") or "—")])
        watchouts.append("Check commute/amenities")
    return {"pros": pros, "watchouts": watchouts, "persona": persona}


@app.post("/api/deedly/analyze")
@app.post("/analyze")
async def deedly_analyze(req: DeedlyAnalyzeRequest):
    """
    Deedly analyze: address + persona → analysisId, property, scores, titleHealth, flags, personaInsights, summary.
    Stores result for /analysis/:id and /ask.
    """
    address = req.address.strip()
    if not address:
        raise HTTPException(status_code=400, detail="Address required")
    persona = (req.persona or "Family").strip() or "Family"

    try:
        geo = await geocode_address(address)
        enrichment = await enrich_property(
            address, geo,
            census_key=os.getenv("CENSUS_API_KEY"),
            walkscore_key=os.getenv("WALKSCORE_API_KEY"),
        )
        transfer = await fetch_transfer_history(address, geo=geo)
        enrichment["transfer_history"] = transfer
        enrichment["transfer_count"] = transfer.get("transfer_count", 0)
        enrichment["last_transfer"] = transfer.get("last_transfer")
        enrichment["transfers"] = transfer.get("transfers", [])[:50]
        enrichment["transfer_source"] = transfer.get("source", "unavailable")
        augmented = _augment_for_frontend(enrichment)
        augmented["risk_summary"] = await generate_risk_summary(augmented)
        augmented["ai_summary"] = augmented["risk_summary"]
        augmented["persona"] = persona
    except Exception as e:
        demo_path = Path(__file__).resolve().parent / "demo_responses.json"
        if demo_path.exists():
            try:
                with open(demo_path) as f:
                    demos = json.load(f)
                demo = demos.get("demo1") or demos.get(list(demos.keys())[0]) if demos else {}
                augmented = demo.get("_raw", demo) if isinstance(demo, dict) else {}
                if not augmented:
                    augmented = demos.get("demo2", {})
                augmented = dict(augmented)
                augmented["address"] = address
                augmented["persona"] = persona
                augmented["ai_summary"] = augmented.get("ai_summary") or augmented.get("summary", "Demo data loaded.")
                augmented["_demo_fallback"] = True
            except Exception:
                raise HTTPException(status_code=502, detail=f"Analysis failed: {e}")
        else:
            raise HTTPException(status_code=502, detail=f"Analysis failed: {e}")

    analysis_id = str(uuid.uuid4())
    deedly = _to_deedly_response(augmented, persona)
    deedly["analysisId"] = analysis_id
    _analysis_store[analysis_id] = augmented
    return {
        "analysisId": analysis_id,
        "property": deedly["property"],
        "scores": deedly["scores"],
        "titleHealth": deedly["titleHealth"],
        "flags": deedly["flags"],
        "personaInsights": deedly["personaInsights"],
        "summary": deedly["summary"],
        "_raw": augmented,
    }


@app.get("/api/analysis/{analysis_id}")
async def get_analysis(analysis_id: str):
    """Return stored analysis by ID."""
    if analysis_id not in _analysis_store:
        raise HTTPException(status_code=404, detail="Analysis not found")
    aug = _analysis_store[analysis_id]
    persona = aug.get("persona", "Family")
    deedly = _to_deedly_response(aug, persona)
    deedly["analysisId"] = analysis_id
    deedly["_raw"] = aug
    return deedly


@app.post("/api/ask")
async def deedly_ask(req: DeedlyAskRequest):
    """AI copilot: answer question using stored analysis. Returns answer, bullets, riskReferences."""
    if req.analysisId not in _analysis_store:
        raise HTTPException(status_code=404, detail="Analysis not found")
    enrichment = _analysis_store[req.analysisId]
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question required")
    answer = await answer_question(question, enrichment)
    bullets = [b.strip() for b in answer.split(".") if b.strip()][:5]
    risk_refs = []
    if "claim" in answer.lower() or "risk" in answer.lower():
        risk_refs.append("Claim likelihood")
    if "flood" in answer.lower():
        risk_refs.append("Flood risk")
    if "safety" in answer.lower() or "crime" in answer.lower():
        risk_refs.append("Safety score")
    return {"answer": answer, "bullets": bullets, "riskReferences": risk_refs}


@app.get("/api/ai/targets")
async def ai_targets():
    """Return list of target keys that have a trained model. Call POST /api/ai/train first to train."""
    targets = get_trained_targets()
    return {"targets": targets}


@app.post("/api/ai/train")
async def ai_train(req: AITrainRequest):
    """
    Train (or retrain) the ML pipeline for a target using only the supplied rows.
    Each row must have "payload" (enrichment JSON) and the target key with a numeric label.
    Optional value_range (e.g. [0, 100]) and tier_thresholds (e.g. [35, 60]) for tier output.
    No hardcoded data; all training data comes from the request.
    """
    if not req.target or not req.rows:
        raise HTTPException(status_code=400, detail="target and rows (non-empty list) required")
    try:
        result = ml_train_from_rows(
            target_key=req.target,
            rows=req.rows,
            value_range=req.value_range,
            tier_thresholds=req.tier_thresholds,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")


@app.post("/api/ai/predict")
async def ai_predict(req: AIPredictRequest):
    """
    Run ML prediction for the given target. Requires that target was trained via POST /api/ai/train.
    Provide analysisId (from a prior analyze/demo) or payload (raw enrichment JSON).
    """
    if not req.target:
        raise HTTPException(status_code=400, detail="target is required")
    raw = None
    if req.analysisId and req.analysisId in _analysis_store:
        raw = _analysis_store[req.analysisId]
    if raw is None and req.payload:
        raw = req.payload
    if raw is None:
        raise HTTPException(
            status_code=400,
            detail="Provide analysisId (from a prior analyze/demo) or payload (raw enrichment JSON)",
        )
    try:
        result = predict_from_raw(raw, target_key=req.target)
        return {
            "ok": True,
            "target": result["target_key"],
            "predicted_value": result["predicted_value"],
            "tier": result.get("tier"),
            "models": result["models"],
            "top_drivers": result["top_drivers"],
            "feature_importance": result["feature_importance"],
            "linear_coefficients": result["linear_coefficients"],
        }
    except RuntimeError as e:
        if "No model trained" in str(e):
            raise HTTPException(
                status_code=503,
                detail=f"Call POST /api/ai/train first with target '{req.target}' and rows.",
            ) from e
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ML prediction failed: {str(e)}")


def _graph_payload(req: GraphRequest) -> dict:
    """Resolve enrichment payload from analysisId or payload. No hardcoded data."""
    if req.analysisId and req.analysisId in _analysis_store:
        return _analysis_store[req.analysisId]
    if req.payload:
        return req.payload
    raise HTTPException(
        status_code=400,
        detail="Provide analysisId (from a prior analyze) or payload (enrichment JSON).",
    )


async def _expand_payload_for_graph(payload: dict) -> dict:
    """
    Add sales_comps to payload when NYC and few/no comps. Expands radius (24mo, limit 40)
    so the graph has enough property nodes for network risk.
    Uses BBL from nyc_property when available (bypasses address parsing); else address/lat.
    """
    nyc = payload.get("nyc_property") or {}
    comps = nyc.get("sales_comps") or []
    pluto = nyc.get("pluto") or {}
    bbl = nyc.get("bbl") or pluto.get("bbl")
    zipcode = pluto.get("zipcode") or _zip_from_address(payload.get("address") or "")
    new_comps = []
    # Path 1: BBL available — fetch comps directly (no address/lat lookup)
    if bbl and len(comps) < 15:
        try:
            new_comps = await fetch_sales_comps_from_bbl(bbl, zipcode=zipcode or None, months=24, limit=40)
        except Exception:
            pass
    # Path 2: address / lat-lng fallback when BBL path fails or BBL missing
    if not new_comps and len(comps) < 15:
        addr = payload.get("address")
        geo = payload.get("geocoded") or {}
        lat, lng = geo.get("lat"), geo.get("lng")
        try:
            new_comps = await fetch_sales_comps_near(address=addr, lat=lat, lng=lng, months=24, limit=40)
        except Exception:
            pass
    if new_comps:
        p = dict(payload)
        nyc2 = dict(nyc)
        merged = list(comps)
        seen = {(c.get("borough"), c.get("block"), c.get("lot")) for c in comps}
        for c in new_comps:
            k = (c.get("borough"), c.get("block"), c.get("lot"))
            if k not in seen:
                seen.add(k)
                merged.append(c)
        nyc2["sales_comps"] = merged[:60]
        p["nyc_property"] = nyc2
        return p
    return payload


def _zip_from_address(address: str) -> str:
    """Extract 5-digit zip from 'City, ST 12345' or similar."""
    m = re.search(r"\b(\d{5})(?:-\d{4})?\b", address or "")
    return m.group(1) if m else ""


@app.get("/api/graph/status")
async def graph_status():
    """Return Property Behavior Network stats: nodes, edges, property count. All data from ingests."""
    try:
        g = get_graph()
        return g.status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/graph/ingest")
async def graph_ingest(req: GraphRequest):
    """
    Add one enrichment payload to the Property Behavior Network.
    Builds nodes (property, tract, owners, violations) and edges from the payload only.
    For NYC, expands with sales_comps (24mo, limit 40) so there are enough property nodes.
    """
    payload = _graph_payload(req)
    payload = await _expand_payload_for_graph(payload)
    try:
        g = get_graph()
        result = g.add_payload(payload)
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/graph/predict")
async def graph_predict(req: GraphRequest):
    """
    Run graph-based network risk: add payload to graph, run embeddings + Isolation Forest.
    For NYC, expands with sales_comps (24mo, limit 40) so there are enough property nodes.
    Returns network_risk_score (anomaly-based), interpretation, and connected-property counts.
    """
    payload = _graph_payload(req)
    payload = await _expand_payload_for_graph(payload)
    try:
        g = get_graph()
        result = g.predict_network_risk(payload)
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/demo")
async def get_demo(
    key: str = Query("demo1", description="demo1 or demo2"),
    address: str | None = Query(None, description="Override address in response"),
    persona: str = Query("Family", description="Buyer persona"),
):
    """Return demo data from demo_responses.json. Used when analyze fails or for demo mode."""
    demo_path = Path(__file__).resolve().parent / "demo_responses.json"
    if not demo_path.exists():
        raise HTTPException(status_code=404, detail="Demo data not available")
    with open(demo_path) as f:
        demos = json.load(f)
    demo_key = key if key in demos else "demo1"
    augmented = dict(demos[demo_key])
    if address and address.strip():
        augmented["address"] = address.strip()
    augmented["persona"] = persona
    augmented["_demo_fallback"] = True
    analysis_id = str(uuid.uuid4())
    deedly = _to_deedly_response(augmented, persona)
    deedly["analysisId"] = analysis_id
    _analysis_store[analysis_id] = augmented
    return {
        "analysisId": analysis_id,
        "property": deedly["property"],
        "scores": deedly["scores"],
        "titleHealth": deedly["titleHealth"],
        "flags": deedly["flags"],
        "personaInsights": deedly["personaInsights"],
        "summary": deedly["summary"],
        "_raw": augmented,
    }


@app.get("/api/report/{analysis_id}")
async def get_report(analysis_id: str):
    """Report-ready object for printable Buyer Confidence Report."""
    if analysis_id not in _analysis_store:
        raise HTTPException(status_code=404, detail="Analysis not found")
    aug = _analysis_store[analysis_id]
    persona = aug.get("persona", "Family")
    deedly = _to_deedly_response(aug, persona)
    risk = aug.get("risk_score") or {}
    return {
        "address": aug.get("address"),
        "deedlyScore": deedly["scores"].get("deedlyScore", 0),
        "titleHealthLevel": deedly["titleHealth"].get("level", "MED"),
        "topFlags": [f["label"] for f in deedly["flags"][:5]],
        "explanation": deedly["summary"],
        "disclaimer": "This report is for informational purposes only. Not a substitute for professional title or legal advice.",
        "generatedAt": aug.get("_timestamp", ""),
    }


@app.post("/nyc-property")
@app.post("/api/nyc-property")
async def nyc_property(req: AnalyzeRequest):
    """
    Full NYC property intelligence — PLUTO, CO, tax class, DOB/HPD violations,
    zoning, misclassification flags. NYC Open Data, no API key.
    Only for NYC addresses (Manhattan, Brooklyn, Bronx, Queens).
    """
    address = req.address.strip()
    if not address:
        raise HTTPException(status_code=400, detail="Address required")
    geo = await geocode_address(address)
    if not geo:
        raise HTTPException(status_code=422, detail="Could not geocode address")
    state_fips = (geo.get("state_fips") or "").zfill(2)
    county_fips = (geo.get("county_fips") or "").zfill(3)
    lat = geo.get("lat")
    lng = geo.get("lng")
    return await fetch_nyc_property_report(address, state_fips, county_fips, lat=lat, lng=lng)


@app.post("/hpd")
@app.post("/api/hpd")
async def hpd(req: AnalyzeRequest):
    """
    HPD (Housing Preservation and Development) violations and complaints for NYC addresses.
    Returns violations and 311 HPD complaints. NYC Open Data, no API key required.
    Only applicable for NYC (Manhattan, Brooklyn, Bronx, Queens).
    """
    address = req.address.strip()
    if not address:
        raise HTTPException(status_code=400, detail="Address required")
    geo = await geocode_address(address)
    if not geo:
        raise HTTPException(status_code=422, detail="Could not geocode address")
    state_fips = (geo.get("state_fips") or "").zfill(2)
    county_fips = (geo.get("county_fips") or "").zfill(3)
    return await fetch_hpd_for_address(address, state_fips, county_fips)


@app.post("/transfer-history")
async def transfer_history(req: AnalyzeRequest):
    """
    Deed transfer history — last ownership transfer and historical transfers (last ~20 years).

    Supported regions:
      - NYC: Geoclient v2 + ACRIS — deeds (NYCGEO_SUBSCRIPTION_KEY — free at api-portal.nyc.gov)
      - Cook County IL (Chicago): Parcel API → PIN + recorder link (free)
      - LA County CA: Assessor PAIS → AIN + recorder link (free)
      - Melissa LookupDeeds: nationwide (MELISSA_PROPERTY_KEY)
    """
    address = req.address.strip()
    if not address:
        raise HTTPException(status_code=400, detail="Address required")
    return await fetch_transfer_history(address)


@app.post("/risk-report")
async def risk_report(req: AnalyzeRequest):
    """
    FEMA National Risk Index — climate/disaster risk for address.
    Geocode → tract GEOID → FEMA NRI ArcGIS. Same logic as environment.py.
    """
    address = req.address.strip()
    if not address:
        raise HTTPException(status_code=400, detail="Address required")

    geo = await geocode_address(address)
    if not geo:
        raise HTTPException(status_code=422, detail="Could not geocode address")

    geoid = geo.get("full_geoid", "")
    if not geoid or len(geoid) < 11:
        raise HTTPException(status_code=422, detail="No census tract found for address")

    climate = await fetch_fema_nri(geoid)
    if not climate.get("available"):
        raise HTTPException(
            status_code=422,
            detail=climate.get("error_message", "No FEMA NRI data for this tract"),
        )

    return {
        "address": address,
        "dataset_version": climate.get("dataset_version"),
        "tract": climate.get("tract"),
        "county": climate.get("county"),
        "state": climate.get("state"),
        "overall_score": climate.get("overall_score"),
        "overall_rating": climate.get("overall_rating"),
        "wildfire_score": climate.get("wildfire_score"),
        "wildfire_rating": climate.get("wildfire_rating"),
        "flood_score": climate.get("flood_score"),
        "flood_rating": climate.get("flood_rating"),
        "earthquake_score": climate.get("earthquake_score"),
        "earthquake_rating": climate.get("earthquake_rating"),
        "hurricane_score": climate.get("hurricane_score"),
        "hurricane_rating": climate.get("hurricane_rating"),
        "tornado_score": climate.get("tornado_score"),
        "tornado_rating": climate.get("tornado_rating"),
        "tsunami_score": climate.get("tsunami_score"),
        "tsunami_rating": climate.get("tsunami_rating"),
        "landslide_score": climate.get("landslide_score"),
        "landslide_rating": climate.get("landslide_rating"),
        "drought_score": climate.get("drought_score"),
        "drought_rating": climate.get("drought_rating"),
        "heatwave_score": climate.get("heatwave_score"),
        "heatwave_rating": climate.get("heatwave_rating"),
        "expected_annual_loss": climate.get("expected_annual_loss"),
        "social_vulnerability": climate.get("social_vulnerability"),
        "community_resilience": climate.get("community_resilience"),
    }


@app.get("/schools")
async def schools(
    lat: float | None = Query(None, description="Latitude"),
    lng: float | None = Query(None, description="Longitude"),
    radius_miles: float = Query(2.0, ge=0.1, le=50.0, description="Search radius in miles"),
    limit: int = Query(10, ge=1, le=50, description="Max number of schools to return"),
):
    """
    NCES public schools near a point. Provide lat/lng, or use POST /api/schools with an address.
    Example: /schools?lat=38.9&lng=-77.03&radius_miles=2&limit=10
    """
    if lat is None or lng is None:
        raise HTTPException(
            status_code=400,
            detail="Missing lat/lng. Example: /schools?lat=38.9&lng=-77.03&radius_miles=2",
        )
    try:
        results = await fetch_nces_public_schools_near(lat, lng, radius_miles, limit)
        return {
            "query": {"lat": lat, "lng": lng, "radius_miles": radius_miles, "limit": limit},
            "count": len(results),
            "schools": results,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch schools: {e!s}",
        )


# ─── Neighborhood Demographics (Census ACS 5-Year) ──────────────────────────────

@app.get(
    "/api/demographics/zip/{zip_code}",
    summary="Demographics by ZIP code",
    description="""
    Neighborhood demographics for a U.S. ZIP (ZCTA). Real Census ACS 5-Year data:
    residency duration, when neighbors moved in, median income, race/ethnicity.
    Example: /api/demographics/zip/10001
    """,
)
async def demographics_by_zip(
    zip_code: str,
    api_key: str | None = Query(None, description="Optional Census API key for higher rate limits"),
):
    if not zip_code.replace(" ", "").isdigit() or len(zip_code.replace(" ", "")) != 5:
        raise HTTPException(status_code=400, detail="zip_code must be a 5-digit number")
    try:
        return await fetch_demographics_by_zip(zip_code, os.getenv("CENSUS_API_KEY") or api_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get(
    "/api/demographics/county",
    summary="Demographics by county",
    description="""
    Neighborhood demographics for a U.S. county. Provide state_fips (2-digit) and county_fips (3-digit).
    Example: state_fips=06&county_fips=059 (Orange County, CA)
    """,
)
async def demographics_by_county_endpoint(
    state_fips: str = Query(..., description="2-digit state FIPS, e.g. 06 California"),
    county_fips: str = Query(..., description="3-digit county FIPS, e.g. 059 Orange County"),
    api_key: str | None = Query(None),
):
    try:
        return await fetch_demographics_by_county(
            state_fips, county_fips, os.getenv("CENSUS_API_KEY") or api_key
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get(
    "/api/demographics/state/{state_fips}",
    summary="Demographics by state",
    description="Statewide demographics. Examples: 36=New York, 06=California",
)
async def demographics_by_state_endpoint(
    state_fips: str,
    api_key: str | None = Query(None),
):
    try:
        return await fetch_demographics_by_state(
            state_fips, os.getenv("CENSUS_API_KEY") or api_key
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/api/demographics")
@app.post("/api/demographics/by-address")
async def demographics_by_address(req: AnalyzeRequest):
    """
    Neighborhood demographics for an address. Geocodes, then fetches Census ACS
    by ZIP (when available) or county. Returns residency, income, race/ethnicity.
    """
    address = req.address.strip()
    if not address:
        raise HTTPException(status_code=400, detail="Address required")
    geo = await geocode_address(address)
    if not geo:
        raise HTTPException(status_code=422, detail="Could not geocode address")
    state_fips = (geo.get("state_fips") or "").zfill(2)
    county_fips = (geo.get("county_fips") or "").zfill(3)
    zip_code = geo.get("zip_code")
    try:
        return await fetch_demographics_for_address(
            state_fips, county_fips, zip_code=zip_code, api_key=os.getenv("CENSUS_API_KEY")
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/api/schools")
async def schools_by_address(req: AnalyzeRequest):
    """
    Public schools near an address. Geocodes the address, then fetches NCES schools within radius.
    """
    address = req.address.strip()
    if not address:
        raise HTTPException(status_code=400, detail="Address required")
    geo = await geocode_address(address)
    if not geo:
        raise HTTPException(status_code=422, detail="Could not geocode address")
    lat = geo.get("lat")
    lng = geo.get("lng")
    if lat is None or lng is None:
        raise HTTPException(status_code=422, detail="No coordinates for address")
    try:
        results = await fetch_nces_public_schools_near(lat, lng, radius_miles=2.0, limit=10)
        return {
            "address": address,
            "query": {"lat": lat, "lng": lng, "radius_miles": 2.0, "limit": 10},
            "count": len(results),
            "schools": results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch schools: {e!s}")


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Answer a buyer question using enrichment + title context.
    Pass enrichment from /api/analyze, or we'll re-run analysis.
    """
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question required")

    enrichment = req.enrichment
    if not enrichment:
        geo = await geocode_address(req.address)
        enrichment = await enrich_property(
            req.address,
            geo,
            census_key=os.getenv("CENSUS_API_KEY"),
            walkscore_key=os.getenv("WALKSCORE_API_KEY"),
        )

    answer = await answer_question(question, enrichment)
    return {"answer": answer}


# Mount frontend last (serves index.html at / and static assets)
frontend_path = Path(__file__).resolve().parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
