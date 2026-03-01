/**
 * Deedly — Buyer Confidence Platform
 * Address + persona → Deedly Score, Title Health, Persona Insights, AI Copilot
 * Interactive cards, flag popovers, no dashboard feel.
 */

const BACKEND_URL = (typeof window !== "undefined" && window.__DEEDLY_BACKEND__) || "";

let currentAnalysis = null;
let currentAnalysisId = null;
let mapInstance = null;
let schoolsLayer = null;
let simulatedClaimLikelihood = null;

const $ = (id) => document.getElementById(id);

// Explanations for common flags (shown in popover on click)
const FLAG_EXPLANATIONS = {
  "Legal risks": "NYC records show HPD violations, DOB issues, or potential misclassification. Review the full title report and violation list before closing.",
  "Easement found": "An easement gives someone else the right to use part of the property (e.g., utility access, shared driveway). Review the deed and title report to understand scope.",
  "High turnover": "Ownership changed frequently. Could signal investor activity, neighborhood volatility, or title issues. Worth asking your agent.",
  "Flood zone": "Property is in a FEMA flood zone. Higher flood risk may affect insurance costs and resale value. Check FEMA maps for exact zone.",
  "HPD violations": "NYC Housing Preservation & Development found violations at this address. Severity varies; review the violation list and status.",
  "Liens": "Claims against the property that must be cleared before transfer. Common: tax, mechanic's, HOA liens.",
  "Open violations": "Unresolved building or housing violations on record. Sellers may need to cure before closing.",
  "Boundary dispute": "Possible boundary or easement dispute in records. Survey and title review recommended.",
  "Recent transfer spike": "Unusual number of recent transfers in the area. Can indicate market volatility or other factors.",
  "Unverified crime data": "Crime data for this area could not be verified. Safety score may be less reliable.",
  "No comps": "Few comparable sales nearby. Valuation and confidence in price may be lower.",
};

function showToast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 3500);
}

function setVisible(id, visible) {
  const el = $(id);
  if (el) el.classList.toggle("hidden", !visible);
}

async function fetchDemoFromApi(address, persona, key = "demo1") {
  const params = new URLSearchParams({ key, persona });
  if (address) params.set("address", address);
  const res = await fetch(`${BACKEND_URL}/api/demo?${params}`);
  if (!res.ok) throw new Error("Demo not available");
  return res.json();
}

// Analyze form
$("analyze-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const address = $("address-input").value.trim();
  if (!address) return;

  const persona = $("persona-select").value || "Family";
  setVisible("empty-state", false);
  setVisible("results", false);
  setVisible("loading-state", true);
  $("analyze-btn").disabled = true;

  try {
    const res = await fetch(`${BACKEND_URL}/api/deedly/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address, persona }),
    });

    let data;
    if (res.ok) {
      data = await res.json();
    } else {
      throw new Error(res.statusText || "Analysis failed");
    }

    if (data._raw?._demo_fallback) {
      showToast("Couldn't analyze address — using demo data");
    }

    currentAnalysis = data;
    currentAnalysisId = data.analysisId;
    simulatedClaimLikelihood = null;
    renderDashboard(data);
    setVisible("loading-state", false);
    setVisible("results", true);
  } catch (err) {
    try {
      showToast("Couldn't analyze address — using demo data from file");
      const data = await fetchDemoFromApi(address, persona, "demo1");
      currentAnalysis = data;
      currentAnalysisId = data.analysisId;
      renderDashboard(data);
      setVisible("loading-state", false);
      setVisible("results", true);
    } catch (demoErr) {
      showToast("Analysis failed. Try a different address or check backend.");
      setVisible("loading-state", false);
      setVisible("empty-state", true);
    }
  } finally {
    $("analyze-btn").disabled = false;
  }
});

$("demo-btn").addEventListener("click", async () => {
  setVisible("empty-state", false);
  setVisible("results", false);
  setVisible("loading-state", true);
  $("demo-btn").disabled = true;
  try {
    const data = await fetchDemoFromApi(null, $("persona-select").value, "demo1");
    $("address-input").value = data.property?.address ?? "";
    currentAnalysis = data;
    currentAnalysisId = data.analysisId;
    renderDashboard(data);
    setVisible("loading-state", false);
    setVisible("results", true);
  } catch (err) {
    showToast("Could not load demo data.");
    setVisible("loading-state", false);
    setVisible("empty-state", true);
  } finally {
    $("demo-btn").disabled = false;
  }
});

$("reset-btn").addEventListener("click", () => {
  $("address-input").value = "";
  currentAnalysis = null;
  currentAnalysisId = null;
  setVisible("results", false);
  setVisible("empty-state", true);
  if (mapInstance) {
    mapInstance.remove();
    mapInstance = null;
  }
});

// Tabs
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((c) => c.classList.remove("active"));
    btn.classList.add("active");
    const tab = btn.getAttribute("data-tab");
    const content = $(`tab-${tab}`);
    if (content) content.classList.add("active");
    if (tab === "title" && mapInstance && currentAnalysis) initMap();
  });
});

// Interactive score cards: click to expand/collapse
document.querySelectorAll(".score-card").forEach((card) => {
  card.addEventListener("click", () => {
    const expanded = card.getAttribute("aria-expanded") === "true";
    document.querySelectorAll(".score-card").forEach((c) => {
      c.setAttribute("aria-expanded", "false");
      const ex = c.querySelector(".card-explain");
      if (ex) ex.hidden = true;
    });
    if (!expanded) {
      card.setAttribute("aria-expanded", "true");
      const ex = card.querySelector(".card-explain");
      if (ex) ex.hidden = false;
    }
  });
});

// Flag popover: click badge to show, click elsewhere to hide
function showFlagPopover(badge, label) {
  const popover = $("flag-popover");
  const text = FLAG_EXPLANATIONS[label] || `"${label}" — a notable item found in the property analysis. Review your full report for details.`;
  popover.textContent = text;
  popover.classList.remove("hidden");

  const rect = badge.getBoundingClientRect();
  popover.style.left = `${rect.left}px`;
  popover.style.top = `${rect.bottom + 8}px`;
}

function hideFlagPopover() {
  $("flag-popover").classList.add("hidden");
}

document.addEventListener("click", (e) => {
  if (e.target.classList.contains("flag-badge")) {
    e.stopPropagation();
    const label = e.target.getAttribute("data-label") || e.target.textContent;
    showFlagPopover(e.target, label);
  } else {
    hideFlagPopover();
  }
});

function renderDashboard(data) {
  const scores = data.scores || {};
  const th = data.titleHealth || {};
  const flags = data.flags || [];
  const personaInsights = data.personaInsights || {};

  const deedlyScore = scores.deedlyScore ?? 0;
  const level = (simulatedClaimLikelihood != null ? (simulatedClaimLikelihood > 12 ? "HIGH" : simulatedClaimLikelihood > 6 ? "MED" : "LOW") : th.level) || "MED";
  const levelKey = level.toUpperCase().replace(/\s+/g, "-");

  $("score-num").textContent = deedlyScore;
  $("title-health-badge").textContent = `TITLE: ${level} RISK`;
  $("title-health-badge").className = "badge badge-" + (levelKey === "LOW" ? "low" : levelKey === "HIGH" ? "high" : "med");

  const safety = scores.safety ?? 0;
  const titleH = scores.titleHealth ?? (100 - deedlyScore);
  const env = scores.environmental ?? 0;
  const nbhd = scores.neighborhoodStability ?? 70;

  $("card-val-safety").textContent = Math.round(safety);
  $("card-val-title").textContent = Math.round(titleH);
  $("card-val-env").textContent = Math.round(env);
  $("card-val-nbhd").textContent = Math.round(nbhd);

  const flagsList = $("flags-list");
  flagsList.innerHTML = flags.length
    ? flags.map((f) => `<button type="button" class="flag-badge ${f.level}" data-label="${(f.label || "").replace(/"/g, "&quot;")}">${f.label}</button>`).join("")
    : `<span class="flag-badge med">None</span>`;

  $("summary-text").textContent = data.summary || "";

  $("turnover").textContent = th.ownership_turnover || "—";
  $("liens").textContent = th.liens || "—";
  $("easements").textContent = th.easements || "—";
  $("zoning").textContent = th.zoning || "—";
  const claim = simulatedClaimLikelihood ?? th.claimLikelihood ?? 5;
  $("claim-likelihood").textContent = claim + "%";

  $("persona-name").textContent = personaInsights.persona || "Family";
  const pros = personaInsights.pros || [];
  const watchouts = personaInsights.watchouts || [];
  $("pros-list").innerHTML = pros.map((p) => `<li>${p}</li>`).join("") || "<li>—</li>";
  $("watchouts-list").innerHTML = watchouts.map((w) => `<li>${w}</li>`).join("") || "<li>—</li>";

  initMap();
  fetchGraphRisk();
}

// Property Behavior Network: ingest then predict (no hardcoding)
function fetchGraphRisk() {
  const loadingEl = $("graph-risk-loading");
  const contentEl = $("graph-risk-content");
  if (!loadingEl || !contentEl) return;
  if (!currentAnalysisId) {
    contentEl.classList.add("hidden");
    return;
  }
  loadingEl.classList.remove("hidden");
  contentEl.classList.add("hidden");
  const body = JSON.stringify({ analysisId: currentAnalysisId });

  fetch(`${BACKEND_URL}/api/graph/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  })
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
    .then(() =>
      fetch(`${BACKEND_URL}/api/graph/predict`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      })
    )
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
    .then((data) => {
      loadingEl.classList.add("hidden");
      contentEl.classList.remove("hidden");
      const score = data.network_risk_score;
      $("graph-risk-score").textContent = score != null ? score : "—";
      $("graph-risk-interpretation").textContent = data.interpretation || "";
      const stats = [];
      if (data.connected_properties != null) stats.push(`Connected properties: ${data.connected_properties}`);
      if (data.same_tract_properties != null) stats.push(`Same tract: ${data.same_tract_properties}`);
      if (data.owner_degree != null) stats.push(`Owner links: ${data.owner_degree}`);
      if (data.feature_inputs?.violation_links != null && data.feature_inputs.violation_links > 0) {
        stats.push(`Violation types: ${data.feature_inputs.violation_links}`);
      }
      $("graph-risk-stats").innerHTML = stats.length ? stats.map((s) => `<li>${s}</li>`).join("") : "";

      // Feature inputs (address-specific explainability)
      const fi = data.feature_inputs || {};
      const fiOrder = [
        "connected_properties",
        "same_tract_properties",
        "owner_links",
        "violation_links",
        "anomaly_raw",
        "total_graph_properties",
        "total_graph_nodes",
        "total_graph_edges",
      ];
      const fiLabels = {
        connected_properties: "Comparable properties (same block)",
        same_tract_properties: "Other properties in census tract",
        owner_links: "Owner links (deeds, PLUTO, tax)",
        violation_links: "Violation types on record",
        anomaly_raw: "Raw anomaly score (Isolation Forest)",
        total_graph_properties: "Properties in graph",
        total_graph_nodes: "Total graph nodes",
        total_graph_edges: "Total graph edges",
      };
      let fiHtml = "";
      for (const k of fiOrder) {
        if (!(k in fi)) continue;
        const v = fi[k];
        if (v == null && k !== "anomaly_raw") continue;
        const label = fiLabels[k] || k.replace(/_/g, " ");
        const val = v != null ? String(v) : "—";
        fiHtml += `<div class="graph-fi-row"><span class="graph-fi-label">${label}</span><span class="graph-fi-value">${val}</span></div>`;
      }
      const fiEl = $("graph-risk-feature-inputs");
      if (fiEl) fiEl.innerHTML = fiHtml || "<p class=\"graph-fi-empty\">No feature inputs available.</p>";

      const explEl = $("graph-risk-score-explanation");
      if (explEl) explEl.textContent = data.score_explanation || "";
      explEl?.classList?.toggle("hidden", !data.score_explanation);

      const factorsEl = $("graph-risk-factors");
      const factors = data.factors || [];
      if (factorsEl) factorsEl.innerHTML = factors.length ? factors.map((f) => `<li>${f}</li>`).join("") : "";
    })
    .catch(() => {
      loadingEl.classList.add("hidden");
      contentEl.classList.remove("hidden");
      $("graph-risk-score").textContent = "—";
      $("graph-risk-interpretation").textContent = "Network risk unavailable (ingest more analyses or check backend).";
      $("graph-risk-stats").innerHTML = "";
      const fiEl = $("graph-risk-feature-inputs");
      if (fiEl) fiEl.innerHTML = "";
      const explEl = $("graph-risk-score-explanation");
      if (explEl) { explEl.textContent = ""; explEl.classList.add("hidden"); }
      const factorsEl = $("graph-risk-factors");
      if (factorsEl) factorsEl.innerHTML = "";
    });
}

$("graph-risk-btn")?.addEventListener("click", () => fetchGraphRisk());

// Map
function initMap() {
  const raw = currentAnalysis?._raw || currentAnalysis;
  const lat = raw?.geocoded?.lat ?? raw?.property?.lat ?? currentAnalysis?.property?.lat;
  const lng = raw?.geocoded?.lng ?? raw?.property?.lng ?? currentAnalysis?.property?.lng;
  const container = $("map-property");
  if (!container || (lat == null || lng == null)) return;

  if (mapInstance) {
    mapInstance.remove();
    mapInstance = null;
  }

  mapInstance = L.map("map-property").setView([lat, lng], 15);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "© OpenStreetMap" }).addTo(mapInstance);
  const score = currentAnalysis?.scores?.deedlyScore ?? 50;
  const radius = 80 + (score * 2);
  L.circle([lat, lng], { radius, color: "#c34a36", fillColor: "#c34a36", fillOpacity: 0.12, weight: 1 })
    .addTo(mapInstance)
    .bindPopup("Risk zone (higher score = larger radius)");
  L.marker([lat, lng]).addTo(mapInstance).bindPopup(currentAnalysis?.property?.address || "Property");

  const schools = raw?.schools || [];
  if (schoolsLayer) {
    mapInstance.removeLayer(schoolsLayer);
  }
  schoolsLayer = L.layerGroup();
  schools.forEach((s) => {
    const loc = s.location;
    if (loc && loc.lat != null && loc.lng != null) {
      L.marker([loc.lat, loc.lng], { icon: L.divIcon({ className: "school-marker", html: "🏫", iconSize: [24, 24] }) })
        .addTo(schoolsLayer)
        .bindPopup(s.name || "School");
    }
  });
  schoolsLayer.addTo(mapInstance);
}

// Simulation modal
$("simulate-btn").addEventListener("click", () => {
  $("simulate-modal").classList.remove("hidden");
});

$("close-modal").addEventListener("click", () => {
  $("simulate-modal").classList.add("hidden");
});

$("run-simulate").addEventListener("click", () => {
  const sel = $("scenario-select").value;
  if (sel === "add_lien") simulatedClaimLikelihood = 15;
  else if (sel === "boundary") simulatedClaimLikelihood = 12;
  else if (sel === "transfer_spike") simulatedClaimLikelihood = 10;
  $("simulate-modal").classList.add("hidden");
  if (currentAnalysis) {
    currentAnalysis.titleHealth = { ...currentAnalysis.titleHealth, claimLikelihood: simulatedClaimLikelihood };
    renderDashboard(currentAnalysis);
  }
  showToast("Simulation applied");
});

// Copilot
$("ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = $("ask-input").value.trim();
  if (!question || !currentAnalysisId) return;

  const messages = $("chat-messages");
  const qDiv = document.createElement("div");
  qDiv.className = "chat-message";
  qDiv.innerHTML = `<div class="question">You: ${question}</div><div class="answer">Thinking…</div>`;
  messages.appendChild(qDiv);
  $("ask-input").value = "";

  try {
    const res = await fetch(`${BACKEND_URL}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ analysisId: currentAnalysisId, question }),
    });
    const data = res.ok ? await res.json() : null;
    const answer = data?.answer || "Could not get answer.";
    qDiv.querySelector(".answer").textContent = answer;
  } catch (err) {
    qDiv.querySelector(".answer").textContent = "Error: " + (err.message || "Request failed");
  }
});

// Actions
$("report-btn").addEventListener("click", () => {
  if (!currentAnalysisId) return;
  const url = `${location.origin}${location.pathname.replace(/\/?$/, "")}/report.html?id=${currentAnalysisId}`;
  window.open(url, "_blank", "width=800,height=600");
});

$("copy-link-btn").addEventListener("click", () => {
  if (!currentAnalysisId) return;
  const url = `${location.href.split("#")[0]}?id=${currentAnalysisId}`;
  navigator.clipboard.writeText(url).then(() => showToast("Link copied to clipboard"));
});

$("download-json-btn").addEventListener("click", () => {
  if (!currentAnalysis) return;
  const blob = new Blob([JSON.stringify(currentAnalysis, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `deedly-report-${currentAnalysisId || "export"}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
  showToast("JSON downloaded");
});
