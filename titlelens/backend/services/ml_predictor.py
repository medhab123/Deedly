"""
Deedly AI / ML Prediction Layer

- Single feature extractor; multiple configurable targets (risk_score, claim_likelihood, value_change, etc.).
- Trained only from real labeled rows supplied via API (no hardcoded seeds).
- Multiple models: Linear Regression, Random Forest, Gradient Boosting, and optionally XGBoost.
- One predictor per target; train and predict by target key.
"""

from __future__ import annotations

from typing import Any

import numpy as np

try:
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import StandardScaler
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

try:
    from xgboost import XGBRegressor
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

# Fixed feature set (same for all targets)
FEATURE_NAMES = [
    "transfer_count",
    "safety_score",
    "flood_score",
    "comps_used",
    "log_median_income",
    "walk_score",
    "transit_score",
    "bike_score",
    "population",
    "school_count",
    "incident_count",
    "legal_risk_encoded",
    "valuation_encoded",
    "estimated_value_log",
]


def _get(d: dict, *keys: str, default: Any = 0) -> Any:
    out = d
    for k in keys:
        out = (out or {}).get(k)
        if out is None:
            return default
    return out


def extract_features(raw: dict) -> dict[str, float]:
    """
    Extract a fixed set of numeric features from raw enrichment JSON.
    Same schema as enrichment / _raw from analyze; no hardcoded defaults beyond safe fallbacks.
    """
    dash = raw.get("confidence_dashboard") or {}
    crime = raw.get("crime") or {}
    climate = raw.get("climate") or {}
    walk = raw.get("walkability") or {}
    demo = raw.get("demographics") or raw.get("neighborhood_demographics") or {}
    val = dash.get("valuation_confidence") or {}
    legal = dash.get("hidden_legal_risks") or {}
    schools = raw.get("schools") or []

    safety = raw.get("safety_score") or _get(dash, "crime_data", "safety_score")
    if safety is None:
        safety = 50
    flood = (climate.get("flood_score") or climate.get("overall_score")) or 0
    comps = val.get("comps_used") or 0
    income = None
    if isinstance(demo.get("income"), dict):
        income = demo["income"].get("median_household_income_usd")
    if income is None:
        income = demo.get("median_income") or demo.get("median_household_income_usd")
    income = income or 60000
    pop = demo.get("population") or (demo.get("race_ethnicity") or {}).get("total_population") or 5000
    incident = crime.get("incident_count") or 200
    est_val = val.get("estimated_value") or (raw.get("demographics") or {}).get("median_home_value") or 0

    legal_level = (legal.get("level") or "").upper()
    if legal_level in ("VERY HIGH",):
        legal_encoded = 3
    elif legal_level in ("HIGH",):
        legal_encoded = 2
    elif legal_level in ("MODERATE",):
        legal_encoded = 1
    else:
        legal_encoded = 0

    val_level = (val.get("level") or "LOW").upper()
    if val_level == "HIGH":
        val_encoded = 2
    elif val_level == "MEDIUM":
        val_encoded = 1
    else:
        val_encoded = 0

    log_income = np.log1p(float(income))
    log_est_val = np.log1p(float(est_val)) if est_val else 0.0

    return {
        "transfer_count": float(raw.get("transfer_count") or 0),
        "safety_score": float(safety),
        "flood_score": float(flood),
        "comps_used": float(comps or 0),
        "log_median_income": log_income,
        "walk_score": float(walk.get("walk_score") or 0),
        "transit_score": float(walk.get("transit_score") or 0),
        "bike_score": float(walk.get("bike_score") or 0),
        "population": float(pop),
        "school_count": float(len(schools)),
        "incident_count": float(incident),
        "legal_risk_encoded": float(legal_encoded),
        "valuation_encoded": float(val_encoded),
        "estimated_value_log": log_est_val,
    }


def _parse_target_value(row: dict, target_key: str) -> float | None:
    """Extract numeric target from a training row. Top-level key, or dot path (e.g. risk_score.score)."""
    # Top-level label
    if target_key in row and row[target_key] is not None:
        try:
            v = row[target_key]
            if isinstance(v, dict) and "score" in v:
                return float(v["score"])
            return float(v)
        except (TypeError, ValueError):
            pass
    # Dot path: resolve from row then from payload
    if "." in target_key:
        for src in (row, row.get("payload") or row):
            cur = src
            for k in target_key.split("."):
                cur = (cur or {}).get(k)
                if cur is None:
                    break
            if cur is not None:
                try:
                    return float(cur)
                except (TypeError, ValueError):
                    pass
    # Single key inside payload
    payload = row.get("payload") or row
    if target_key in payload and payload[target_key] is not None:
        try:
            v = payload[target_key]
            if isinstance(v, dict) and "score" in v:
                return float(v["score"])
            return float(v)
        except (TypeError, ValueError):
            pass
    return None


class MLPredictor:
    """
    One predictor per target. Trained only from supplied rows (payload + label).
    Models: Linear Regression, Random Forest, Gradient Boosting, and optionally XGBoost.
    """

    def __init__(self, target_key: str):
        if not HAS_SKLEARN:
            raise RuntimeError("sklearn is required for ML predictor. pip install scikit-learn")
        self.target_key = target_key
        self.scaler = StandardScaler()
        self.lr = LinearRegression()
        self.rf = RandomForestRegressor(n_estimators=80, max_depth=8, random_state=42)
        self.gb = GradientBoostingRegressor(n_estimators=60, max_depth=4, random_state=42)
        self.xgb = None
        if HAS_XGBOOST:
            self.xgb = XGBRegressor(n_estimators=60, max_depth=4, random_state=42)
        self.feature_names = FEATURE_NAMES
        self._trained = False
        self.value_range: list[float] | None = None  # [min, max] for clipping
        self.tier_thresholds: list[float] | None = None  # e.g. [35, 60] -> LOW < 35, MED < 60, HIGH

    def train_from_rows(
        self,
        rows: list[dict],
        value_range: list[float] | None = None,
        tier_thresholds: list[float] | None = None,
    ) -> None:
        """
        Train on real labeled rows. Each row must have "payload" (enrichment JSON)
        and the target key (or nested path) with a numeric label.
        """
        if not rows:
            raise ValueError("At least one training row required")
        X_list = []
        y_list = []
        for row in rows:
            payload = row.get("payload") or row
            y_val = _parse_target_value(row, self.target_key)
            if y_val is None:
                continue
            feats = extract_features(payload)
            X_list.append([feats[n] for n in self.feature_names])
            y_list.append(y_val)
        if len(y_list) < 2:
            raise ValueError("Need at least two rows with valid target values")
        X = np.array(X_list, dtype=np.float64)
        y = np.array(y_list, dtype=np.float64)

        self.value_range = value_range
        self.tier_thresholds = tier_thresholds
        if value_range and len(value_range) >= 2:
            y = np.clip(y, value_range[0], value_range[1])

        X_scaled = self.scaler.fit_transform(X)
        self.lr.fit(X_scaled, y)
        self.rf.fit(X, y)
        self.gb.fit(X, y)
        if self.xgb is not None:
            self.xgb.fit(X, y)
        self._trained = True

    def predict(self, raw: dict) -> dict[str, Any]:
        """Run all trained models; return ensemble, per-model outputs, and explainability."""
        if not self._trained:
            raise RuntimeError(f"No model trained for target '{self.target_key}'. Call POST /api/ai/train first.")
        feats = extract_features(raw)
        x = np.array([[feats[n] for n in self.feature_names]], dtype=np.float64)
        x_scaled = self.scaler.transform(x)

        preds = {}
        pred_lr = float(self.lr.predict(x_scaled)[0])
        pred_rf = float(self.rf.predict(x)[0])
        pred_gb = float(self.gb.predict(x)[0])
        preds["linear_regression"] = pred_lr
        preds["random_forest"] = pred_rf
        preds["gradient_boosting"] = pred_gb
        if self.xgb is not None:
            pred_xgb = float(self.xgb.predict(x)[0])
            preds["xgboost"] = pred_xgb

        # Ensemble weights: 4 models -> equal-ish; 3 models -> no xgb
        if self.xgb is not None:
            weights = {"linear_regression": 0.2, "random_forest": 0.35, "gradient_boosting": 0.25, "xgboost": 0.2}
        else:
            weights = {"linear_regression": 0.25, "random_forest": 0.40, "gradient_boosting": 0.35}
        ensemble = sum(preds[k] * weights.get(k, 0) for k in preds if k in weights)

        if self.value_range and len(self.value_range) >= 2:
            ensemble = max(self.value_range[0], min(self.value_range[1], ensemble))

        tier = None
        if self.tier_thresholds and len(self.tier_thresholds) >= 2:
            t1, t2 = self.tier_thresholds[0], self.tier_thresholds[1]
            if ensemble < t1:
                tier = "LOW"
            elif ensemble < t2:
                tier = "MED"
            else:
                tier = "HIGH"

        imp = self.rf.feature_importances_
        importance_list = [{"feature": name, "importance": float(imp[i])} for i, name in enumerate(self.feature_names)]
        importance_list.sort(key=lambda t: -t["importance"])
        top_drivers = [t["feature"] for t in importance_list[:5]]

        coef = self.lr.coef_
        coefficients = [{"feature": name, "coefficient": float(coef[i])} for i, name in enumerate(self.feature_names)]
        coefficients.sort(key=lambda t: -abs(t["coefficient"]))

        return {
            "target_key": self.target_key,
            "predicted_value": round(ensemble, 4),
            "tier": tier,
            "models": {k: round(v, 4) for k, v in preds.items()},
            "feature_importance": importance_list,
            "top_drivers": top_drivers,
            "linear_coefficients": coefficients[:7],
            "features_used": feats,
        }


# One predictor per target; no global seeds
_predictors: dict[str, MLPredictor] = {}


def get_predictor(target_key: str) -> MLPredictor | None:
    return _predictors.get(target_key)


def get_trained_targets() -> list[str]:
    """Return list of target keys that have a trained model."""
    return [k for k, p in _predictors.items() if p._trained]


def train_from_rows(
    target_key: str,
    rows: list[dict],
    value_range: list[float] | None = None,
    tier_thresholds: list[float] | None = None,
) -> dict[str, Any]:
    """
    Train or retrain the predictor for the given target using only the supplied rows.
    Returns summary (n_rows, models used).
    """
    if not HAS_SKLEARN:
        raise RuntimeError("sklearn is required. pip install scikit-learn")
    if not target_key or not isinstance(rows, list):
        raise ValueError("target and rows (list) required")
    predictor = _predictors.get(target_key)
    if predictor is None:
        predictor = MLPredictor(target_key=target_key)
        _predictors[target_key] = predictor
    predictor.train_from_rows(rows, value_range=value_range, tier_thresholds=tier_thresholds)
    models = ["linear_regression", "random_forest", "gradient_boosting"]
    if predictor.xgb is not None:
        models.append("xgboost")
    n_used = sum(1 for r in rows if _parse_target_value(r, target_key) is not None)
    return {
        "ok": True,
        "target": target_key,
        "n_rows": len(rows),
        "n_rows_used": n_used,
        "models": models,
    }


def predict_from_raw(raw: dict, target_key: str) -> dict[str, Any]:
    """Run prediction for the given target. Fails if that target was never trained."""
    predictor = get_predictor(target_key)
    if predictor is None or not predictor._trained:
        raise RuntimeError(
            f"No model trained for target '{target_key}'. Call POST /api/ai/train with target and rows first."
        )
    return predictor.predict(raw)
