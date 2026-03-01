# Property Behavior Network (Graph AI)

Instead of asking *"Is this property risky?"* from rules alone, this layer asks:

**"Does this property behave like other problematic properties in the ownership/violation network?"**

All data comes from your APIs and enrichment payloads. Nothing is hardcoded.

---

## What It Does

1. **Builds a graph** from each enrichment payload you ingest:
   - **Nodes:** property (BBL or address), census tract, owners (from deeds/PLUTO/tax), violation types (HPD/DOB).
   - **Edges:** property–tract, property–owner, property–violation, property–same_block–property (from sales comps).

2. **Random-walk embeddings** (DeepWalk-style) run on the graph and learn embeddings for every node. Property-node embeddings capture “who owns what, what violations, which block/tract.”

3. **Isolation Forest** runs on property embeddings. High anomaly ⇒ the property’s *position in the network* is unusual (e.g. similar to high-risk clusters). That becomes the **network risk score** (0–100).

4. **Interpretation** is returned in plain language, e.g. *“This property’s position in the ownership/violation network is anomalous — similar to patterns seen in higher-risk clusters.”*

---

## API

| Method | Endpoint | Purpose |
|--------|----------|--------|
| GET | `/api/graph/status` | Nodes, edges, property count (all from ingests). |
| POST | `/api/graph/ingest` | Body: `{ "analysisId": "..." }` or `{ "payload": {...} }`. Adds one enrichment payload to the graph. |
| POST | `/api/graph/predict` | Same body. Adds payload if new, runs graph embeddings + anomaly. Returns `network_risk_score`, `interpretation`, `connected_properties`, `same_tract_properties`, `owner_degree`. |

- Use **analysisId** when the analysis is already stored (e.g. from `/api/deedly/analyze` or `/api/demo`).
- Use **payload** when you have the raw enrichment JSON (e.g. from your own pipeline).

---

## Flow (No Hardcoding)

1. Your backend produces enrichment (e.g. via analyze or your APIs).
2. You call **POST /api/graph/ingest** with that analysis (by ID or payload). The graph grows.
3. When you want a network risk for a property, call **POST /api/graph/predict** with the same analysis. The service adds the property if new, re-runs graph embeddings and Isolation Forest, and returns the score and interpretation.
4. **NYC addresses** get automatic expansion (24mo sales comps, limit 40) so a single ingest yields many property nodes. Non-NYC or single-property graphs return a neutral score (50) with guidance.

---

## Why This Is “Real AI”

- **Graph structure** is learned from data (owners, violations, geography, comps).
- **Graph embeddings** are learned from random walks — no hand-written rules for “risk.”
- **Anomaly detection** finds properties that sit in unusual network positions (ownership/violation patterns).
- No Zillow/Redfin/title systems model the city as a *network* of properties, owners, and violations in this way.

---

## Dependencies

- `networkx` — graph construction.
- `numpy` + `scikit-learn` — random-walk embeddings + Isolation Forest.

No `node2vec` or `gensim` required (works on Python 3.13 + numpy 2.x).
