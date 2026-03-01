export type BuyerPersona = 'family' | 'investor' | 'first-time' | 'remote-worker'

export interface AnalysisRequest {
  address: string
  persona: BuyerPersona
}

export interface RiskScores {
  safety: number
  titleHealth: number
  environmentalRisk: number
  neighborhoodStability: number
}

export interface NetworkRiskFeatureInputs {
  connected_properties?: number
  same_tract_properties?: number
  owner_links?: number
  violation_links?: number
  anomaly_raw?: number
}

export interface NetworkRisk {
  score: number
  interpretation: string
  ownerDegree: number
  sameTractCount: number
  connectedFlaggedProperties: number
  /** Human-readable factors that influenced the score */
  factors?: string[]
  /** Raw inputs to the anomaly model */
  featureInputs?: NetworkRiskFeatureInputs
  /** Full score calculation explanation */
  scoreExplanation?: string
}

export interface TitleHealthData {
  ownershipTurnoverFrequency: string
  liens: string[]
  encumbrances: string[]
  easements: string[]
  zoningStability: string
  estimatedClaimLikelihood: number
}

export interface PersonaInsight {
  label: string
  value: string
  sentiment: 'positive' | 'neutral' | 'warning'
}

export interface Signal {
  label: string
  type: 'info' | 'warning' | 'danger' | 'success'
}

export interface AnalysisResult {
  id: string
  address: string
  persona: BuyerPersona
  deedlyScore: number
  verdict: string
  titleRiskLevel: 'LOW' | 'MED' | 'HIGH'
  riskScores: RiskScores
  networkRisk: NetworkRisk
  titleHealth: TitleHealthData
  signals: Signal[]
  aiSummary: string
  soWhat: string
  personaPros: PersonaInsight[]
  personaWatchOuts: PersonaInsight[]
  timestamp: string
  coordinates: { lat: number; lng: number }
}

export interface CopilotMessage {
  role: 'user' | 'assistant'
  content: string
}

export type LoadingStep = {
  label: string
  done: boolean
}
