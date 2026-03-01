"""
Property Behavior Network — graph over properties, owners, violations, and geography.

Builds a graph from enrichment payloads only (no hardcoded data). Uses Node2Vec for
graph embeddings and Isolation Forest for anomaly-based "network risk" so we can say:
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
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

try:
    from node2vec import Node2Vec
    HAS_NODE2VEC = True
except ImportError:
    HAS_NODE2VEC = False

try:
    from sklearn.ensemble import IsolationForest
    import numpy as np
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

    def _run_node2vec(self) -> None:
        """Run Node2Vec and store embeddings for property nodes only."""
        if not HAS_NODE2VEC:
            raise RuntimeError("node2vec is required. pip install node2vec")
        if not HAS_SKLEARN or np is None:
            raise RuntimeError("numpy and sklearn required for embeddings")
        prop_nodes = [n for n in self._g.nodes() if is_property_node(n)]
        if len(prop_nodes) < 2:
            self._property_embeddings = {n: [0.0] * self._embed_dim for n in prop_nodes}
            return
        try:
            # Use largest connected component so random walks don't get stuck
            if not nx.is_connected(self._g):
                comps = list(nx.connected_components(self._g))
                largest = max(comps, key=len)
                sub = self._g.subgraph(largest).copy()
            else:
                sub = self._g
            n2v = Node2Vec(
                sub,
                dimensions=self._embed_dim,
                walk_length=20,
                num_walks=50,
                workers=1,
                quiet=True,
            )
            model = n2v.fit()
            self._property_embeddings = {}
            for n in prop_nodes:
                if n in model.wv:
                    self._property_embeddings[n] = model.wv[n].tolist()
                else:
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
        self._run_node2vec()
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
        out["connected_properties"] = len([n for n in neighbors if is_property_node(n)])
        out["owner_degree"] = len([n for n in neighbors if n.startswith(PREFIX_OWNER)])

        tract = _tract_id(payload)
        if tract and self._g.has_node(tract):
            tract_neighbors = list(self._g.neighbors(tract))
            out["same_tract_properties"] = len([n for n in tract_neighbors if is_property_node(n)])

        if self._iforest is not None and prop in self._property_embeddings:
            X = np.array([self._property_embeddings[prop]], dtype=np.float64)
            score = float(self._iforest.decision_function(X)[0])
            # decision_function: more negative = more anomalous. Map to 0-100 risk (higher = riskier).
            risk = max(0.0, min(100.0, 50.0 - 100.0 * score))
            out["network_risk_score"] = round(risk, 2)
            out["anomaly_raw"] = round(score, 4)
            if score < -0.1:
                out["interpretation"] = "This property's position in the ownership/violation network is anomalous — similar to patterns seen in higher-risk clusters."
            else:
                out["interpretation"] = "This property's network pattern is within the typical range for the current graph."
        else:
            out["interpretation"] = "Not enough properties in the graph yet to compute network risk. Ingest more analyses."

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
