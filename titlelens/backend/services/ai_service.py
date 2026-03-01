"""
AI service — buyer summary and chat using enrichment + title context.
Supports: Google Gemini (free tier, preferred), OpenAI (fallback).
Set GEMINI_API_KEY or OPENAI_API_KEY in .env.
"""

import json
import os
from pathlib import Path
from typing import Optional

import httpx

# Ensure .env is loaded (backend/.env)
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


_GEMINI_MODELS_CACHE: Optional[list[str]] = None


async def _get_gemini_models(key: str) -> list[str]:
    """Fetch available Gemini models from ListModels API. Prefer flash models for speed."""
    global _GEMINI_MODELS_CACHE
    if _GEMINI_MODELS_CACHE is not None:
        return _GEMINI_MODELS_CACHE
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
            )
            if r.status_code != 200:
                return []
            data = r.json()
            models = data.get("models") or []
            names = []
            for m in models:
                name = m.get("name", "")
                if name.startswith("models/"):
                    name = name[7:]
                if name and "generateContent" in str(m.get("supportedGenerationMethods", [])):
                    names.append(name)
            # Prefer flash models (faster, free tier)
            flash = [n for n in names if "flash" in n.lower()]
            others = [n for n in names if n not in flash]
            _GEMINI_MODELS_CACHE = (flash or others)[:5]
            return _GEMINI_MODELS_CACHE
    except Exception:
        return []


async def _call_gemini(prompt: str, system_instruction: str, max_tokens: int = 200) -> tuple[Optional[str], Optional[str]]:
    """Call Google Gemini API (free tier). Returns (response_text, error_msg)."""
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        return None, "GEMINI_API_KEY not set in .env"
    models = await _get_gemini_models(key)
    if not models:
        models = ["gemini-2.0-flash-exp", "gemini-1.5-flash-8b", "gemini-1.0-pro"]
    full_prompt = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt
    payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
    }
    last_err = None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for model in models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                r = await client.post(url, json=payload)
                if r.status_code == 200:
                    data = r.json()
                    candidates = data.get("candidates") or []
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts") or []
                        if parts:
                            text = parts[0].get("text", "").strip()
                            if text:
                                return text, None
                last_err = f"Gemini API {r.status_code}: {r.text[:200]}"
        return None, last_err or "Gemini returned no valid response"
    except httpx.HTTPStatusError as e:
        body = (e.response.text or "")[:300]
        return None, f"Gemini API {e.response.status_code}: {body}"
    except Exception as e:
        return None, f"Gemini error: {type(e).__name__}: {e}"


async def _call_openai(messages: list[dict], max_tokens: int) -> Optional[str]:
    """Call OpenAI API. Returns response text or None."""
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=key)
        r = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=max_tokens,
        )
        return (r.choices[0].message.content or "").strip()
    except Exception:
        return None


async def generate_summary(enrichment: dict) -> str:
    """Generate a 2-3 sentence buyer confidence summary from enrichment data."""
    dash = enrichment.get("confidence_dashboard") or {}
    title = enrichment.get("title", {})
    env = enrichment.get("environmental", {})
    demo = enrichment.get("demographics", {})
    nbhd = enrichment.get("neighborhood_demographics") or {}
    crime = enrichment.get("crime") or {}
    hpd = enrichment.get("hpd") or {}
    nyc = enrichment.get("nyc_property") or {}
    walk = enrichment.get("walkability") or {}

    # Build evidence-rich context so the AI can cite specific numbers
    evidence = {
        "address": enrichment.get("address"),
        "ownership_confidence": dash.get("ownership_confidence", {}).get("level") or title.get("ownership_confidence"),
        "hidden_legal_risks": dash.get("hidden_legal_risks", {}).get("detail") or title.get("hidden_legal_risks"),
        "hpd_violation_count": (hpd.get("violation_count") or 0) + (nyc.get("hpd_violation_count") or 0),
        "flood_risk_level": dash.get("flood_risk", {}).get("level"),
        "flood_score": dash.get("flood_risk", {}).get("score") or env.get("flood_score"),
        "crime_status": dash.get("crime_data", {}).get("status"),
        "crime_incident_count": crime.get("incident_count"),
        "safety_score": enrichment.get("safety_score"),
        "valuation_confidence": dash.get("valuation_confidence", {}).get("level"),
        "comps_used": (nyc.get("valuation") or {}).get("comps_used"),
        "estimated_value": (nyc.get("valuation") or {}).get("estimated_value"),
        "median_income": demo.get("median_income") or (nbhd.get("income") or {}).get("median_household_income_usd"),
        "walk_score": walk.get("walk_score"),
        "transit_score": walk.get("transit_score"),
        "bike_score": walk.get("bike_score"),
        "insurance_risk": dash.get("insurance_risk", {}).get("level"),
    }

    system = (
        "You are a helpful real estate advisor. Write a brief 2-3 sentence buyer confidence summary. "
        "CITE SPECIFIC EVIDENCE from the data: use actual numbers (e.g. '34 HPD violations', 'flood score 98/100', "
        "'safety score 70/100', 'median income $85,000', '12 comparable sales'). Do not use vague phrases like "
        "'some risks' or 'moderate'; use the exact values provided. Be factual and reassuring. No bullet points."
    )
    prompt = f"Summarize this property for a buyer. Use these values as evidence:\n{json.dumps(evidence, indent=2)}\n\nWrite 2-3 sentences citing specific numbers."

    # Try Gemini first (free tier), then OpenAI
    out, gemini_err = await _call_gemini(prompt, system, max_tokens=250)
    if out:
        return out
    out = await _call_openai(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=250,
    )
    if out:
        return out
    return f"AI summary failed. {gemini_err or 'No AI key configured.'}" if gemini_err else _fallback_summary(enrichment)


async def generate_risk_summary(enrichment: dict) -> str:
    """
    Generate an AI property risk summary using ALL enrichment data.
    Cites specific evidence from the JSON: flood score, HPD violations, crime, etc.
    """
    risk_score = enrichment.get("risk_score") or {}
    score_val = risk_score.get("score", 0)
    level = risk_score.get("level", "UNKNOWN")
    justification = risk_score.get("justification", [])

    system = (
        "You are a property risk analyst. Write a 3-5 sentence AI summary of this property's risk profile. "
        "Use ALL the data provided. CITE SPECIFIC EVIDENCE: flood score, HPD violation count, safety score, "
        "crime incident count, valuation confidence, CO status, insurance risk, etc. Start with the overall "
        "risk level and score, then summarize the key risk factors with their specific values. Be factual "
        "and direct. No bullet points. End with a brief recommendation (e.g. 'Review recommended' or 'Proceed with due diligence')."
    )
    prompt = (
        f"Property risk score: {score_val}/100 ({level})\n"
        f"Score justification: {json.dumps(justification)}\n\n"
        f"Full property data:\n{json.dumps(enrichment, indent=2)}\n\n"
        f"Write an AI property risk summary (3-5 sentences) citing specific values from the data."
    )

    out, gemini_err = await _call_gemini(prompt, system, max_tokens=2048)
    if out:
        return out
    out = await _call_openai(
        [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        max_tokens=2048,
    )
    if out:
        return out
    return (
        f"Property risk score: {score_val}/100 ({level}). "
        f"Key factors: {'; '.join(justification[:5]) if justification else 'No significant risks identified.'}"
    )


# What the chatbot can answer (docstring for reference; also in system prompt)
_CHAT_SCOPE = """
This chatbot answers questions using ONLY the property enrichment JSON. It can answer about:

- **Ownership & legal risks:** HPD violation count, DOB violations, CO status, misclassification flags
- **Flood & climate:** Flood score/rating, FEMA NRI scores, insurance risk level
- **Crime & safety:** Incident count, safety score, crime data quality (verified/unverified)
- **Valuation:** Comparable sales count, estimated value, valuation confidence
- **Demographics:** Median income, population, race/ethnicity, years at residence (Census ACS)
- **Walkability:** Walk score, transit score, bike score
- **Schools:** Nearby public schools (NYC/NCES)
- **NYC-specific:** PLUTO data, tax class, zoning, ACRIS deeds (NYC addresses only)

It cannot answer: off-topic questions, predictions, legal advice, or anything not in the data.
Always cite specific values from the JSON (e.g. "based on 34 HPD violations" or "flood score is 98/100").
"""


async def answer_question(question: str, enrichment: dict) -> str:
    """Answer a buyer question using enrichment + title context."""
    system = (
        "You are a helpful title/real estate advisor. Answer the buyer's question using ONLY the property data provided. "
        "CITE SPECIFIC EVIDENCE from the JSON: use actual numbers (e.g. '34 HPD violations', 'flood score 98/100'). "
        "You can answer about: ownership/legal risks (HPD, DOB, CO status), flood/climate scores, crime/safety, "
        "valuation/comps, demographics (income, population), walkability, schools, NYC property data. "
        "If the question is outside this scope or data is missing, say so. Be concise (2-5 sentences)."
    )
    context = json.dumps(enrichment, indent=2)
    prompt = f"Property data:\n{context}\n\nBuyer asks: {question}"

    # Try Gemini first (free tier), then OpenAI
    out, gemini_err = await _call_gemini(prompt, system, max_tokens=600)
    if out:
        return out
    out = await _call_openai(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1000,
    )
    if out:
        return out
    return f"AI chat failed. {gemini_err}" if gemini_err else _fallback_answer(question, enrichment)


def _fallback_summary(enrichment: dict) -> str:
    return (
        "AI summary is disabled. Set GEMINI_API_KEY (free at https://aistudio.google.com/apikey) "
        "or OPENAI_API_KEY in .env. The dashboard values come from live backend APIs where available."
    )


def _fallback_answer(question: str, enrichment: dict) -> str:
    return (
        "AI chat is disabled. Set GEMINI_API_KEY (free at https://aistudio.google.com/apikey) "
        "or OPENAI_API_KEY in .env. Please review the dashboard metrics, which come from live backend APIs."
    )
