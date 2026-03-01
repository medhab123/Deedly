# TitleLens Implementation Plan — Step by Step

## Overview

**Stack:** Python (FastAPI) backend + HTML/CSS/vanilla JS frontend

**Architecture:**
```
User enters address → Frontend (HTML) → Backend API → Data Enrichment Pipeline → Response
                                                    ↓
                              Geocoding → Parallel API calls → Combine → AI Summary
```

---

## Phase 1: Project Setup (Day 1 — 1–2 hours)

### Step 1.1 — Backend scaffold
- [x] Create `backend/` folder
- [x] `requirements.txt` with: `fastapi`, `uvicorn`, `httpx`, `python-dotenv`, `openai` (or `anthropic`)
- [x] `backend/main.py` — FastAPI app with CORS
- [x] `.env.example` — API key placeholders

### Step 1.2 — Frontend scaffold
- [x] Create `frontend/` folder
- [x] `index.html` — main page with address search
- [x] `styles.css` — layout and dashboard styling
- [x] `app.js` — fetch calls, DOM updates

### Step 1.3 — API keys
Register for:
- Census API: https://api.census.gov/data/key_signup.html
- Walk Score: https://walkscore.com/professional/api.php
- FEMA NRI: no key needed
- Census Geocoder: no key needed
- OpenAI or Anthropic: for AI summary

---

## Phase 2: Geocoding & Core Pipeline (Day 1–2 — 2–3 hours)

### Step 2.1 — Geocoding service
- Input: street address
- Output: `lat`, `lng`, `census_tract`, `state`, `county_fips`
- Use **Census Geocoder** (free, no key):  
  `https://geocoding.geo.census.gov/geocoder/locations/address`

### Step 2.2 — Backend endpoint
- `POST /api/analyze` — body: `{ "address": "123 Main St, Chicago, IL" }`
- Returns combined enrichment data (mock first, then real)

---

## Phase 3: Data Enrichment Services (Day 2–3 — 4–5 hours)

Run these **in parallel** after geocoding (use `asyncio.gather` or `httpx` async):

| Priority | API | Data | Key? |
|----------|-----|------|------|
| 1 | Census Geocoder | lat, lng, tract | No |
| 2 | FEMA National Risk Index | flood, fire, wind risk | No |
| 3 | Census API | income, population, housing | Yes |
| 4 | Regrid / ATTOM | ownership, zoning | Yes (free tier) |
| 5 | Walk Score | walk, transit, bike | Yes |
| 6 | City Open Data (Chicago/NYC/Austin) | crime | No (Socrata) |
| 7 | FRED | regional price index | Yes |

**Fallback strategy:** If an API fails, return partial data + note in UI (e.g., “Crime data not available for this area”).

---

## Phase 4: Mock Title Data (Day 2 — 1 hour)

- Create `backend/mock_title_data.json` — sample ownership history, liens, easements
- Map address → mock record by city/zip
- Real ATTOM/Regrid can replace this when keys are ready

---

## Phase 5: AI Summary & Chat (Day 3 — 2 hours)

### Step 5.1 — Summary generation
- Endpoint: `POST /api/summary` or included in `/api/analyze`
- Input: combined enrichment object
- Prompt: “Given this property data, write a 2–3 sentence buyer confidence summary.”
- Output: natural language summary

### Step 5.2 — Chat endpoint
- Endpoint: `POST /api/chat`
- Body: `{ "address": "...", "question": "Is this property safe long term?" }`
- Use enrichment + title mock as context
- LLM answers using both datasets

---

## Phase 6: Frontend Dashboard (Day 3–4 — 3–4 hours)

### Step 6.1 — Search UI
- Input: address
- Button: “Get Property Report”
- Loading state

### Step 6.2 — Property Confidence Dashboard
Display:
- Ownership Confidence: HIGH / MEDIUM / LOW
- Hidden Legal Risks: LOW / MODERATE / HIGH
- Neighborhood Safety: 78/100
- Flood Risk: Low / Moderate / High
- Future Value Trend: +9% projected
- Community Profile: short text
- Insurance Risk Impact: Low / Medium / High

### Step 6.3 — AI Chat
- Text input: “Ask about this property…”
- Submit → `/api/chat` → display AI response

---

## Phase 7: Polish & Demo (Day 4–5 — 2 hours)

- [ ] Demo cities: Chicago, NYC, Austin (where crime data exists)
- [ ] Add “Data coverage” disclaimer in UI
- [ ] 2-minute demo script
- [ ] README with setup instructions

---

## File Structure (Final)

```
titlelens/
├── backend/
│   ├── main.py              # FastAPI app, routes
│   ├── services/
│   │   ├── geocoder.py      # Census Geocoder
│   │   ├── enrichment.py    # FEMA, Census, Walk Score, etc.
│   │   └── ai_service.py    # LLM summary + chat
│   ├── mock_title_data.json
│   ├── requirements.txt
│   └── .env
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── IMPLEMENTATION_PLAN.md
└── README.md
```

---

## Quick Start Commands

```bash
# Backend
cd titlelens/backend
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
# Add .env with API keys
uvicorn main:app --reload --port 8000

# Frontend — served by backend at /
# Or open frontend/index.html and point API to http://localhost:8000
```

---

## Demo Script (2 min)

1. Enter “123 N State St, Chicago, IL”
2. Click “Get Property Report”
3. Show dashboard: ownership, risks, safety, flood
4. Ask: “Is this property safe long term?”
5. Show AI answer using title + enrichment data
6. Pitch: “We integrate title data with neighborhood intelligence to give buyers confidence before closing.”
