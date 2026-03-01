'use client'

import { useState } from 'react'
import type { AnalysisResult } from '@/lib/types'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { TrendingUp, FlaskConical } from 'lucide-react'

type Scenario = 'lien' | 'boundary' | 'transfer'

const SCENARIOS: { value: Scenario; label: string; description: string }[] = [
  { value: 'lien', label: 'Add Old Lien', description: 'Simulate discovery of a previously unrecorded lien from 10+ years ago' },
  { value: 'boundary', label: 'Boundary Dispute', description: 'Simulate a neighbor filing a boundary/encroachment dispute' },
  { value: 'transfer', label: 'Transfer Spike', description: 'Simulate a sudden spike in ownership transfers in the tract' },
]

function simulateScenario(base: number, scenario: Scenario): { score: number; delta: number } {
  const impacts: Record<Scenario, number> = {
    lien: -12,
    boundary: -8,
    transfer: -15,
  }
  const delta = impacts[scenario]
  return { score: Math.max(0, Math.min(100, base + delta)), delta }
}

export function TitleHealthTab({ analysis }: { analysis: AnalysisResult }) {
  const [simOpen, setSimOpen] = useState(false)
  const [selectedScenario, setSelectedScenario] = useState<Scenario | null>(null)
  const [simResult, setSimResult] = useState<{ score: number; delta: number } | null>(null)

  const handleSimulate = () => {
    if (!selectedScenario) return
    const result = simulateScenario(analysis.riskScores.titleHealth, selectedScenario)
    setSimResult(result)
  }

  const handleCloseSimulation = () => {
    setSimOpen(false)
    setSelectedScenario(null)
    setSimResult(null)
  }

  const { titleHealth } = analysis

  return (
    <div className="flex flex-col gap-6 animate-fade-lift-in">
      {/* Ownership Turnover */}
      <div className="glass-card rounded-xl p-6">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="size-4 text-teal" />
          <h3 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
            Ownership Turnover
          </h3>
        </div>
        <p className="font-sans text-sm text-cream">{titleHealth.ownershipTurnoverFrequency}</p>
      </div>

      {/* Zoning Stability */}
      <div className="glass-card rounded-xl p-6">
        <h3 className="mb-2 font-mono text-xs uppercase tracking-widest text-muted-foreground">
          Zoning Stability
        </h3>
        <p className="font-sans text-sm text-cream">{titleHealth.zoningStability}</p>
      </div>

      {/* Simulate Scenario Button */}
      <button
        onClick={() => setSimOpen(true)}
        className="flex items-center justify-center gap-2 rounded-xl border border-teal/30 bg-teal/5 px-6 py-3.5 font-mono text-sm text-teal transition-all hover:bg-teal/10"
      >
        <FlaskConical className="size-4" />
        Simulate Scenario
      </button>

      {/* Simulation Modal */}
      <Dialog open={simOpen} onOpenChange={handleCloseSimulation}>
        <DialogContent className="bg-card border-border text-cream">
          <DialogHeader>
            <DialogTitle className="font-serif text-xl text-cream">Simulate Scenario</DialogTitle>
            <DialogDescription className="font-sans text-sm text-muted-foreground">
              See how hypothetical scenarios would impact the title health score.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-3 py-2">
            {SCENARIOS.map((s) => (
              <button
                key={s.value}
                onClick={() => { setSelectedScenario(s.value); setSimResult(null) }}
                className={`rounded-lg border p-3 text-left transition-all ${
                  selectedScenario === s.value
                    ? 'border-teal bg-teal/10'
                    : 'border-border bg-secondary/20 hover:border-teal/30'
                }`}
              >
                <span className="font-mono text-xs font-medium text-cream">{s.label}</span>
                <p className="mt-1 font-sans text-xs text-muted-foreground">{s.description}</p>
              </button>
            ))}
          </div>

          {simResult && (
            <div className="rounded-lg border border-amber/20 bg-amber/5 p-4">
              <div className="flex items-center gap-2 mb-2">
                <Badge variant="outline" className="border-amber/30 text-amber font-mono text-[10px]">
                  SIMULATED
                </Badge>
              </div>
              <div className="flex items-baseline gap-2">
                <span className="font-serif text-2xl text-cream">{simResult.score}</span>
                <span className="font-mono text-xs text-destructive">({simResult.delta})</span>
              </div>
              <p className="mt-1 font-mono text-xs text-muted-foreground">
                Simulated title health score after scenario applied
              </p>
            </div>
          )}

          <DialogFooter>
            <button
              onClick={handleSimulate}
              disabled={!selectedScenario}
              className="rounded-lg bg-teal px-4 py-2 font-mono text-xs font-medium text-primary-foreground transition-colors hover:bg-teal/90 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Run Simulation
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
