# Deedly AI / ML Prediction Layer

This document describes the **AI layer** on top of the enrichment JSON: configurable targets, multiple models (including optional XGBoost), and training only from real labeled data supplied via API. **Nothing is hardcoded.**

---

## Idea

1. **Single feature extractor** — same enrichment JSON schema for all targets.
2. **Configurable target** — train and predict for any numeric outcome: `risk_score`, `claim_likelihood`, `value_change`, `estimated_value`, or any key you supply. Change the target by training with new rows and that target key.
3. **Real data only** — training is done via `POST /api/ai/train` with a list of labeled rows (each row: `payload` + your target key). No built-in seeds or synthetic data.
4. **Multiple models** — Linear Regression, Random Forest, Gradient Boosting, and **XGBoost** (if installed). Ensemble combines them; feature importance and coefficients explain the prediction.
5. **Optional tier** — when training you can pass `value_range` (e.g. [0, 100]) and `tier_thresholds` (e.g. [35, 60]) so predictions return a tier (LOW / MED / HIGH).

---

## Data Used

All inputs come from the **enrichment JSON** (e.g. from `/api/deedly/analyze` or `/api/demo`, or the `_raw` / `demo_responses.json` shape). No extra APIs.

| Feature | Source in JSON |
|--------|-----------------|
| `transfer_count` | Top-level |
| `safety_score` | Top-level or `confidence_dashboard.crime_data` |
| `flood_score` | `climate` |
| `comps_used` | `confidence_dashboard.valuation_confidence` |
| `log_median_income` | `demographics` / `neighborhood_demographics` |
| `walk_score`, `transit_score`, `bike_score` | `walkability` |
| `population` | `demographics` |
| `school_count` | `len(schools)` |
| `incident_count` | `crime` |
| `legal_risk_encoded` | `confidence_dashboard.hidden_legal_risks.level` (0–3) |
| `valuation_encoded` | `confidence_dashboard.valuation_confidence.level` (0–2) |
| `estimated_value_log` | Valuation / demographics |

---

## Models

All models use the **same feature vector**; the **target** is whatever you pass when training.

| Model | Role |
|-------|------|
| **Linear Regression** (standardized features) | Interpretable coefficients. |
| **Random Forest** | Non-linear patterns; feature importance. |
| **Gradient Boosting** | Strong prediction; importance view. |
| **XGBoost** (optional) | Extra model when `xgboost` is installed; included in ensemble. |

- **Ensemble:** weighted average (e.g. LR 0.25, RF 0.40, GB 0.35 without XGBoost; with XGBoost all four get weights). Output is clipped to `value_range` when provided.
- **Tier:** optional; only if you pass `tier_thresholds` at train time (e.g. [35, 60] → LOW &lt; 35, MED &lt; 60, HIGH).

---

## Training Data (Real Only)

**No hardcoded or synthetic data.** You supply all training rows via the API:

1. **POST /api/ai/train** — body: `target`, `rows` (each row: `payload` = enrichment JSON, plus the target key with numeric label). Optional: `value_range`, `tier_thresholds`.
2. Rows can come from your own APIs, DB, or exports; the backend never injects seeds.
3. You can train multiple targets (e.g. `risk_score`, `claim_likelihood`); each target has its own model. Retraining the same target overwrites that model.

---

## API

- **`GET /api/ai/targets`**  
  Returns `{ "targets": ["risk_score", ...] }` — list of target keys that have a trained model.

- **`POST /api/ai/train`**  
  Body: `{ "target": "risk_score", "rows": [ { "payload": {...}, "risk_score": 52 }, ... ], "value_range": [0, 100], "tier_thresholds": [35, 60] }`.  
  All training data comes from `rows`; no hardcoded data. Optional: `value_range` (clip predictions), `tier_thresholds` (return tier).

- **`POST /api/ai/predict`**  
  Body: `{ "target": "risk_score", "analysisId": "<id>" }` or `{ "target": "risk_score", "payload": {...} }`.  
  `target` must be one of the keys returned by `GET /api/ai/targets` (must have been trained first).

Response includes:

- `predicted_value`, `tier` (if configured)
- `models`: per-model scores (including `xgboost` when available)
- `top_drivers`, `feature_importance`, `linear_coefficients`

---

## Explainability

- **Feature importance** (from Random Forest): which inputs matter most for the predicted score.
- **Linear coefficients**: direction and magnitude of each feature in the linear model (in scaled space).
- **Top drivers**: human-readable list shown in the UI so users see “what drove this score.”

---

## Extending the Layer

- **Other targets:** Call `POST /api/ai/train` with a different `target` and new `rows`; same feature extractor. E.g. `target: "claim_likelihood"` or `target: "value_change"` with rows that have that key.
- **More models:** XGBoost is already optional; add more in `ml_predictor.py` and register in the ensemble.
- **Real data:** All training is real data from your request; persist models to disk in your backend if you need them across restarts.
