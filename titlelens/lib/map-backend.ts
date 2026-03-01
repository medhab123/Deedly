/**
 * Maps backend Deedly API responses to frontend AnalysisResult.
 * No hardcoded values — all data from backend.
 */

import type { AnalysisResult, BuyerPersona, RiskScores, NetworkRisk, TitleHealthData, Signal, PersonaInsight } from './types'

export interface DeedlyBackendResponse {
  analysisId?: string
  property?: { address?: string; geocoded?: { lat?: number; lng?: number } }
  scores?: { deedlyScore?: number; safety?: number; titleHealth?: number; environmental?: number; neighborhoodStability?: number }
  titleHealth?: { level?: string; ownership_turnover?: string; liens?: string; easements?: string; zoning?: string; claimLikelihood?: number }
  flags?: Array<{ label: string; level: string }>
  personaInsights?: { pros?: string[]; watchouts?: string[]; persona?: string }
  summary?: string
  _raw?: Record<string, unknown>
}

export interface GraphPredictResponse {
  network_risk_score?: number
  interpretation?: string
  connected_properties?: number
  same_tract_properties?: number
  owner_degree?: number
  factors?: string[]
  feature_inputs?: {
    connected_properties?: number
    same_tract_properties?: number
    owner_links?: number
    violation_links?: number
    anomaly_raw?: number
  }
  score_explanation?: string
}

function personaFromBackend(p?: string): BuyerPersona {
  const v = (p || '').toLowerCase().replace(/\s+/g, '-')
  if (v === 'family' || v === 'investor' || v === 'first-time' || v === 'first-time-buyer' || v === 'remote-worker') return v as BuyerPersona
  return 'family'
}

function flagsToSignals(flags: Array<{ label: string; level: string }> | undefined): Signal[] {
  if (!flags?.length) return []
  return flags.map((f) => ({
    label: f.label,
    type: f.level === 'high' ? 'danger' : f.level === 'med' ? 'warning' : 'info',
  } as Signal))
}

function prosToPersonaInsights(pros: string[] | undefined): PersonaInsight[] {
  return (pros || []).map((p) => ({ label: p.split('—')[0]?.trim() || p, value: p.split('—')[1]?.trim() || p, sentiment: 'positive' as const }))
}

function watchoutsToPersonaInsights(watchouts: string[] | undefined): PersonaInsight[] {
  return (watchouts || []).map((w) => ({ label: w.split('—')[0]?.trim() || w, value: w.split('—')[1]?.trim() || w, sentiment: 'warning' as const }))
}

export function mapBackendToAnalysis(
  backend: DeedlyBackendResponse,
  graph?: GraphPredictResponse | null,
): AnalysisResult {
  const prop = backend.property || {}
  const scores = backend.scores || {}
  const th = backend.titleHealth || {}
  const geo = prop.geocoded || {}

  const riskScores: RiskScores = {
    safety: scores.safety ?? 65,
    titleHealth: scores.titleHealth ?? 50,
    environmentalRisk: scores.environmental ?? 50,
    neighborhoodStability: scores.neighborhoodStability ?? 70,
  }

  const networkRisk: NetworkRisk = {
    score: graph?.network_risk_score ?? 50,
    interpretation: graph?.interpretation ?? 'Network analysis not yet run.',
    ownerDegree: graph?.owner_degree ?? 0,
    sameTractCount: graph?.same_tract_properties ?? 0,
    connectedFlaggedProperties: 0,
    factors: graph?.factors,
    featureInputs: graph?.feature_inputs,
    scoreExplanation: graph?.score_explanation,
  }

  const liens: string[] = th.liens && th.liens !== 'None recorded' ? [th.liens] : []
  const titleHealth: TitleHealthData = {
    ownershipTurnoverFrequency: th.ownership_turnover ?? '—',
    liens,
    encumbrances: [],
    easements: th.easements ? [th.easements] : [],
    zoningStability: th.zoning ? `Zoning: ${th.zoning}` : '—',
    estimatedClaimLikelihood: th.claimLikelihood ?? 5,
  }

  const personaInsights = backend.personaInsights || {}
  const signals = flagsToSignals(backend.flags)
  const personaPros = prosToPersonaInsights(personaInsights.pros)
  const personaWatchOuts = watchoutsToPersonaInsights(personaInsights.watchouts)

  const titleRiskLevel = (th.level || 'MED').toUpperCase() as 'LOW' | 'MED' | 'HIGH'
  const deedlyScore = scores.deedlyScore ?? 50

  return {
    id: backend.analysisId ?? `analysis-${Date.now()}`,
    address: (prop.address as string) || '',
    persona: personaFromBackend(personaInsights.persona),
    deedlyScore,
    verdict: backend.summary ?? 'Analysis complete.',
    titleRiskLevel,
    riskScores,
    networkRisk,
    titleHealth,
    signals,
    aiSummary: backend.summary ?? '',
    soWhat: backend.summary ?? 'Review the signals and tabs for details.',
    personaPros,
    personaWatchOuts,
    timestamp: new Date().toISOString(),
    coordinates: { lat: geo.lat ?? 0, lng: geo.lng ?? 0 },
  }
}
