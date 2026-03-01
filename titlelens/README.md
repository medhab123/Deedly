# TitleLens — Buyer Intelligence for Title Insurance

**One-line pitch:** Integrate title insurance data with enriched neighborhood intelligence to give buyers a real-time understanding of risk, safety, and ownership confidence before closing.

## Stack

- **Backend:** Python (FastAPI)
- **Frontend:** HTML, CSS, vanilla JavaScript
- **APIs:** Census Geocoder, Census API, FEMA NRI, Walk Score (optional keys)
- **AI:** OpenAI (optional, for AI summary and chat)

## Quick Start

### 1. Backend setup

```bash
cd titlelens/backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Optional: API keys

Copy `.env.example` to `.env` and add keys for richer data:

```
CENSUS_API_KEY=       # api.census.gov/data/key_signup.html
WALKSCORE_API_KEY=    # walkscore.com/professional/api.php
OPENAI_API_KEY=       # For AI summary + chat
```

Without keys: geocoding (Census Geocoder) works; enrichment uses mock/estimated data; AI uses fallback text.

### 3. Run

```bash
cd titlelens/backend
uvicorn main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

### 4. Demo flow

1. Enter address (e.g. `123 N State St, Chicago, IL`)
2. Click **Get Property Report**
3. View the Property Confidence Dashboard
4. Ask a question: *"Is this property safe long term?"*

## Project structure

```
titlelens/
├── backend/
│   ├── main.py              # FastAPI app, routes
│   ├── services/
│   │   ├── geocoder.py      # Census Geocoder
│   │   ├── enrichment.py    # FEMA, Census, Walk Score, mock title
│   │   └── ai_service.py    # AI summary + chat
│   ├── mock_title_data.json
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── IMPLEMENTATION_PLAN.md
└── README.md
```

## APIs used

| API              | Key? | Data                          |
|------------------|------|-------------------------------|
| Census Geocoder  | No   | lat, lng, tract               |
| Census API       | Yes  | income, population, housing   |
| FEMA NRI         | No   | flood, hazard risk            |
| Walk Score       | Yes  | walk, transit, bike scores    |
| Mock title       | —    | ownership, liens, zoning      |

## Demo cities

Mock title data is available for: **Chicago**, **New York**, **Austin**, **Los Angeles**. Other addresses use default mock data.
