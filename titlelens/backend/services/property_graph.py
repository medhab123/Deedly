"""
Property Behavior Network — graph over properties, owners, violations, and geography.

Builds a graph from enrichment payloads only (no hardcoded data). Uses random-walk
embeddings (DeepWalk-style, no node2vec/gensim) and Isolation Forest for anomaly-based
"network risk" so we can say:
"Does this property behave like other problematic properties?" / "Connected to N
properties in a high-risk pattern."

Nodes: property (BBL or address), tract, owner (from deeds/PLUTO/tax), violation (type).
Edges: property-in-tract, property-has-owner, property-has-violation, property-same_block-property.
"""

from __future__ import annotations

import re
from typing import Any

try:
    import networkx as nx
    import numpy as np
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    np = None

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.utils.extmath import randomized_svd
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

# Prefixes for node IDs (consistent across ingests)
PREFIX_PROPERTY = "p:"
PREFIX_TRACT = "t:"
PREFIX_OWNER = "o:"
PREFIX_VIOLATION = "v:"


def _norm(s: str | None) -> str:
    if s is None or not isinstance(s, str):
        return ""
    return re.sub(r"\s+", " ", s.strip()).upper() or ""


def _prop_id(payload: dict) -> str:
    """Stable property node ID from payload."""
    nyc = payload.get("nyc_property") or {}
    bbl = nyc.get("bbl")
    if bbl and str(bbl).strip():
        return PREFIX_PROPERTY + str(bbl).strip()
    addr = payload.get("address") or ""
    return PREFIX_PROPERTY + ("addr:" + _norm(addr) if addr else "addr:unknown")


def _tract_id(payload: dict) -> str | None:
    geo = payload.get("geocoded") or {}
    tract = geo.get("tract_geoid") or geo.get("tract") or geo.get("full_geoid")
    if tract and str(tract).strip():
        return PREFIX_TRACT + str(tract).strip()
    return None


def _owner_ids(payload: dict) -> list[str]:
    """Collect owner-like node IDs from deeds, PLUTO, tax."""
    out = set()
    nyc = payload.get("nyc_property") or {}
    for deed in nyc.get("acris_deeds") or []:
        for key in ("grantor", "grantee"):
            name = deed.get(key)
            if name and isinstance(name, str) and _norm(name):
                out.add(PREFIX_OWNER + _norm(name))
    pluto = nyc.get("pluto") or {}
    own = pluto.get("ownername")
    if own and _norm(own):
        out.add(PREFIX_OWNER + _norm(own))
    tax = nyc.get("tax") or {}
    if isinstance(tax, dict):
        owner = tax.get("owner")
        if owner and _norm(owner):
            out.add(PREFIX_OWNER + _norm(owner))
    transfers = payload.get("transfers") or payload.get("transfer_history", {}).get("transfers") or []
    for t in transfers:
        for key in ("grantor", "grantee"):
            name = t.get(key)
            if name and _norm(name):
                out.add(PREFIX_OWNER + _norm(name))
    return list(out)


def _violation_ids(payload: dict) -> list[str]:
    """Violation-type nodes from DOB and HPD."""
    out = set()
    nyc = payload.get("nyc_property") or {}
    for v in nyc.get("dob_violations") or []:
        cat = (v.get("violation_category") or "").strip() or "dob"
        vtype = (v.get("violation_type") or v.get("violation_type_code") or "").strip() or "unknown"
        out.add(PREFIX_VIOLATION + _norm(f"dob:{cat}:{vtype}"))
    for v in nyc.get("hpd_violations") or []:
        cl = (v.get("class") or "").strip() or "unknown"
        out.add(PREFIX_VIOLATION + _norm(f"hpd:class{cl}"))
    hpd = payload.get("hpd") or {}
    for v in hpd.get("violations") or []:
        cl = (v.get("class") or "").strip() or "unknown"
        out.add(PREFIX_VIOLATION + _norm(f"hpd:class{cl}"))
    return list(out)


def _same_block_property_ids(payload: dict) -> list[str]:
    """Other property nodes from sales_comps (same block) so we get same_block edges."""
    out = []
    nyc = payload.get("nyc_property") or {}
    comps = nyc.get("sales_comps") or []
    pluto = nyc.get("pluto") or {}
    borough = (pluto.get("borough") or nyc.get("borough") or "").strip()
    block = pluto.get("block")
    if block is None:
        for c in comps:
            b = c.get("borough")
            bl = c.get("block")
            lot = c.get("lot")
            if b and bl is not None and lot is not None:
                out.append(PREFIX_PROPERTY + f"{b}-{bl}-{lot}")
        return list(set(out))
    for c in comps:
        b = c.get("borough") or borough
        bl = c.get("block")
        lot = c.get("lot")
        if b and bl is not None and lot is not None:
            out.append(PREFIX_PROPERTY + f"{b}-{bl}-{lot}")
    return list(set(out))


def build_edges_from_payload(payload: dict) -> list[tuple[str, str, str]]:
    """
    From one enrichment payload, produce list of (u, v, edge_type) for the graph.
    All data comes from the payload; nothing hardcoded.
    """
    edges = []
    prop = _prop_id(payload)
    tract = _tract_id(payload)
    if tract:
        edges.append((prop, tract, "in_tract"))
    for oid in _owner_ids(payload):
        edges.append((prop, oid, "has_owner"))
    for vid in _violation_ids(payload):
        edges.append((prop, vid, "has_violation"))
    for other in _same_block_property_ids(payload):
        if other != prop:
            edges.append((prop, other, "same_block"))
    return edges


def is_property_node(n: str) -> bool:
    return n.startswith(PREFIX_PROPERTY)


class PropertyGraph:
    """
    In-memory graph + Node2Vec embeddings + Isolation Forest anomaly.
    All content comes from ingest payloads; no built-in seeds.
    """

    def __init__(self):
        if not HAS_NETWORKX:
            raise RuntimeError("networkx is required for property graph. pip install networkx")
        self._g = nx.Graph()
        self._property_embeddings: dict[str, list[float]] = {}
        self._iforest = None
        self._embed_dim = 32
        self._last_embed_version = 0

    def add_payload(self, payload: dict) -> dict[str, Any]:
        """
        Ingest one enrichment payload: add nodes and edges to the graph.
        Returns counts added (properties, edges, etc.).
        """
        edges = build_edges_from_payload(payload)
        prop = _prop_id(payload)
        self._g.add_node(prop, node_type="property")
        added_edges = 0
        for u, v, etype in edges:
            self._g.add_node(v, node_type=("tract" if v.startswith(PREFIX_TRACT) else "owner" if v.startswith(PREFIX_OWNER) else "violation" if v.startswith(PREFIX_VIOLATION) else "property"))
            if not self._g.has_edge(u, v):
                self._g.add_edge(u, v, edge_type=etype)
                added_edges += 1
        self._last_embed_version += 1
        return {
            "property_id": prop,
            "edges_from_payload": len(edges),
            "edges_added": added_edges,
            "total_nodes": self._g.number_of_nodes(),
            "total_edges": self._g.number_of_edges(),
        }

    def _run_embeddings(self) -> None:
        """Random-walk + SVD embeddings (no node2vec/gensim). Uses networkx + numpy + sklearn only."""
        if not HAS_SKLEARN or np is None:
            raise RuntimeError("numpy and sklearn required for embeddings")
        prop_nodes = [n for n in self._g.nodes() if is_property_node(n)]
        if len(prop_nodes) < 2:
            self._property_embeddings = {n: [0.0] * self._embed_dim for n in prop_nodes}
            return
        try:
            if not nx.is_connected(self._g):
                comps = list(nx.connected_components(self._g))
                largest = max(comps, key=len)
                sub = self._g.subgraph(largest).copy()
            else:
                sub = self._g
            nodes = list(sub.nodes())
            n_nodes = len(nodes)
            node_idx = {u: i for i, u in enumerate(nodes)}
            # Co-occurrence from random walks (DeepWalk-style)
            n_walks, walk_len = 80, 20
            window = 3
            cooc = np.zeros((n_nodes, n_nodes), dtype=np.float64)
            for _ in range(n_walks):
                start = np.random.choice(nodes)
                walk = [start]
                for _ in range(walk_len - 1):
                    neigs = list(sub.neighbors(walk[-1]))
                    if not neigs:
                        break
                    walk.append(np.random.choice(neigs))
                for i, u in enumerate(walk):
                    for j in range(max(0, i - window), min(len(walk), i + window + 1)):
                        if i != j:
                            ui, uj = node_idx.get(u), node_idx.get(walk[j])
                            if ui is not None and uj is not None:
                                cooc[ui, uj] += 1
            cooc = np.log1p(cooc)
            U, _, _ = randomized_svd(cooc, n_components=min(self._embed_dim, n_nodes - 1), random_state=42)
            emb = np.zeros((n_nodes, self._embed_dim), dtype=np.float64)
            emb[:, : U.shape[1]] = U
            self._property_embeddings = {n: emb[node_idx[n]].tolist() for n in prop_nodes if n in node_idx}
            for n in prop_nodes:
                if n not in self._property_embeddings:
                    self._property_embeddings[n] = [0.0] * self._embed_dim
        except Exception:
            self._property_embeddings = {n: [0.0] * self._embed_dim for n in prop_nodes}

    def _fit_anomaly(self) -> None:
        """Fit Isolation Forest on current property embeddings."""
        if not HAS_SKLEARN or np is None:
            return
        prop_nodes = [n for n in self._property_embeddings]
        if len(prop_nodes) < 2:
            self._iforest = None
            return
        X = np.array([self._property_embeddings[n] for n in prop_nodes], dtype=np.float64)
        self._iforest = IsolationForest(random_state=42, contamination="auto", n_estimators=100)
        self._iforest.fit(X)

    def predict_network_risk(self, payload: dict) -> dict[str, Any]:
        """
        Add payload to graph if new, run Node2Vec, run anomaly detection.
        Returns network_risk_score (anomaly: higher = more unusual/risky), and summary stats.
        """
        prop = _prop_id(payload)
        self.add_payload(payload)
        self._run_embeddings()
        self._fit_anomaly()

        out = {
            "property_id": prop,
            "network_risk_score": None,
            "interpretation": None,
            "connected_properties": 0,
            "same_tract_properties": 0,
            "owner_degree": 0,
            "total_graph_nodes": self._g.number_of_nodes(),
            "total_graph_edges": self._g.number_of_edges(),
        }

        if prop not in self._property_embeddings:
            out["interpretation"] = "Property not in graph or embedding failed."
            return out

        # Connected properties (neighbors via any edge)
        neighbors = list(self._g.neighbors(prop))
        connected_props = len([n for n in neighbors if is_property_node(n)])
        owner_deg = len([n for n in neighbors if n.startswith(PREFIX_OWNER)])
        violation_deg = len([n for n in neighbors if n.startswith(PREFIX_VIOLATION)])
        out["connected_properties"] = connected_props
        out["owner_degree"] = owner_deg

        tract = _tract_id(payload)
        same_tract = 0
        if tract and self._g.has_node(tract):
            tract_neighbors = list(self._g.neighbors(tract))
            same_tract = len([n for n in tract_neighbors if is_property_node(n)])
        out["same_tract_properties"] = same_tract

        n_props = len([n for n in self._g.nodes() if is_property_node(n)])
        total_nodes = self._g.number_of_nodes()
        total_edges = self._g.number_of_edges()

        # Feature inputs (what went into the score)
        out["feature_inputs"] = {
            "connected_properties": connected_props,
            "same_tract_properties": same_tract,
            "owner_links": owner_deg,
            "violation_links": violation_deg,
            "anomaly_raw": None,
            "total_graph_properties": n_props,
            "total_graph_nodes": total_nodes,
            "total_graph_edges": total_edges,
        }

        if self._iforest is not None and prop in self._property_embeddings and len(self._property_embeddings) >= 2:
            X = np.array([self._property_embeddings[prop]], dtype=np.float64)
            score = float(self._iforest.decision_function(X)[0])
            # decision_function: more negative = more anomalous. Map to 0-100 risk (higher = riskier).
            risk = max(0.0, min(100.0, 50.0 - 100.0 * score))
            out["network_risk_score"] = round(risk, 2)
            out["anomaly_raw"] = round(score, 4)
            out["feature_inputs"]["anomaly_raw"] = round(score, 4)

            # Build address-specific score explanation
            addr = (payload.get("address") or "").strip() or "This property"
            factors: list[str] = []
            if connected_props == 0:
                factors.append("No comparable sales nearby — limited context")
            elif connected_props < 5:
                factors.append(f"Only {connected_props} comparable properties in same block")
            else:
                factors.append(f"{connected_props} comparable properties linked (same block)")

            if same_tract > 0:
                factors.append(f"{same_tract} other property(ies) in same census tract")
            if owner_deg > 0:
                factors.append(f"{owner_deg} owner link(s) (deeds, PLUTO, tax records)")
            if violation_deg > 0:
                factors.append(f"{violation_deg} violation type(s) on record — raises anomaly")

            if score < -0.1:
                factors.append("Graph embedding flagged as anomalous vs typical pattern")
                out["interpretation"] = f"{addr} sits in a network position similar to higher-risk clusters. Isolation Forest anomaly score {round(score, 3)} (negative = unusual)."
            else:
                factors.append("Graph embedding within typical range")
                out["interpretation"] = f"{addr} fits the typical network pattern for this graph. Anomaly score {round(score, 3)} (near zero = normal)."

            out["factors"] = factors
            out["score_explanation"] = (
                f"Score {out['network_risk_score']} from Isolation Forest on graph embeddings. "
                f"Your property connects to {connected_props} comps, {same_tract} tract neighbors, {owner_deg} owner(s), {violation_deg} violation type(s). "
                f"Raw anomaly {round(score, 3)} → mapped to 0–100 risk."
            )
        else:
            if n_props < 2:
                out["network_risk_score"] = 50.0
                out["interpretation"] = "Single property in graph; network risk requires 2+ properties. Use NYC addresses for automatic expansion, or ingest more analyses."
                out["factors"] = ["Insufficient graph size — need 2+ properties to compute"]
                out["score_explanation"] = "Score 50 (neutral) — graph has only 1 property. Add more NYC addresses to build a meaningful network."
            else:
                out["interpretation"] = "Graph embeddings or anomaly model not ready; retry after ingesting more analyses."
                out["factors"] = []
                out["score_explanation"] = None

        return out

    def status(self) -> dict[str, Any]:
        """Return graph stats (no hardcoded data)."""
        prop_nodes = [n for n in self._g.nodes() if is_property_node(n)]
        return {
            "nodes": self._g.number_of_nodes(),
            "edges": self._g.number_of_edges(),
            "property_nodes": len(prop_nodes),
            "embedding_version": self._last_embed_version,
            "has_anomaly_model": self._iforest is not None,
        }


# Single global graph (no hardcoded content)
_graph: PropertyGraph | None = None


def get_graph() -> PropertyGraph:
    global _graph
    if _graph is None:
        _graph = PropertyGraph()
    return _graph
