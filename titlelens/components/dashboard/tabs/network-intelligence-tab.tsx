'use client'

import type { AnalysisResult } from '@/lib/types'
import { ChevronRight, Info, Network } from 'lucide-react'

export function NetworkIntelligenceTab({ analysis }: { analysis: AnalysisResult }) {
  const { networkRisk } = analysis
  const showStats = networkRisk.ownerDegree >= 2
  const hasFactors = networkRisk.factors && networkRisk.factors.length > 0
  const featureInputs = networkRisk.featureInputs

  return (
    <div className="flex flex-col gap-6 animate-fade-lift-in">
      {/* Hero card */}
      <div className="glass-card rounded-xl border border-teal/20 p-8">
        <div className="mb-6 flex items-center gap-2">
          <Network className="size-5 text-teal" />
          <span className="font-mono text-xs uppercase tracking-widest text-teal">
            Graph Intelligence
          </span>
        </div>

        {/* Score display */}
        <div className="flex items-center gap-6 mb-6">
          <div className="flex flex-col items-center">
            <span className="font-serif text-5xl text-cream">{networkRisk.score}</span>
            <span className="mt-1 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Network Score
            </span>
          </div>
          <div className="h-16 w-px bg-border" />
          <p className="flex-1 font-sans text-sm leading-relaxed text-muted-foreground">
            {networkRisk.interpretation}
          </p>
        </div>

        {/* Network stats */}
        {showStats ? (
          <div className="mt-6 flex flex-col gap-3">
            <div className="flex items-center justify-between rounded-lg bg-secondary/30 px-4 py-3">
              <span className="font-mono text-xs text-muted-foreground">Owner controls</span>
              <span className="font-mono text-sm font-medium text-cream">{networkRisk.ownerDegree} properties</span>
            </div>
            <div className="flex items-center justify-between rounded-lg bg-secondary/30 px-4 py-3">
              <span className="font-mono text-xs text-muted-foreground">Same-tract properties</span>
              <span className="font-mono text-sm font-medium text-cream">{networkRisk.sameTractCount}</span>
            </div>
            <div className="flex items-center justify-between rounded-lg bg-secondary/30 px-4 py-3">
              <span className="font-mono text-xs text-muted-foreground">Connected flagged properties</span>
              <span className="font-mono text-sm font-medium text-cream">{networkRisk.connectedFlaggedProperties}</span>
            </div>
          </div>
        ) : (
          <div className="mt-6 rounded-lg bg-secondary/30 p-4">
            <p className="font-sans text-sm leading-relaxed text-muted-foreground">
              Building network... This signal strengthens as more properties are
              analyzed — you are among the first.
            </p>
          </div>
        )}
      </div>

      {/* Score calculation & factors */}
      {(hasFactors || featureInputs || networkRisk.scoreExplanation) && (
        <div className="glass-card rounded-xl p-6">
          <h3 className="mb-4 flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-teal">
            <Info className="size-3.5" />
            How the score is calculated
          </h3>

          {/* Full explanation from backend */}
          {networkRisk.scoreExplanation && (
            <p className="mb-5 font-sans text-sm leading-relaxed text-cream/90">
              {networkRisk.scoreExplanation}
            </p>
          )}

          {/* Factors influencing the score */}
          {hasFactors && (
            <div className="mb-5">
              <h4 className="mb-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Factors influencing this score
              </h4>
              <ul className="flex flex-col gap-2">
                {networkRisk.factors!.map((factor, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 rounded-lg bg-secondary/20 px-3 py-2 font-sans text-sm text-cream/90"
                  >
                    <ChevronRight className="mt-0.5 size-3.5 shrink-0 text-teal/70" />
                    {factor}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Feature inputs — quantitative breakdown */}
          {featureInputs && (
            <div>
              <h4 className="mb-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Inputs by category
              </h4>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {featureInputs.connected_properties != null && (
                  <div className="rounded-lg border border-border/50 bg-secondary/10 px-3 py-2">
                    <span className="block font-mono text-[10px] uppercase text-muted-foreground">Comps in block</span>
                    <span className="font-mono text-lg font-medium text-cream">{featureInputs.connected_properties}</span>
                  </div>
                )}
                {featureInputs.same_tract_properties != null && (
                  <div className="rounded-lg border border-border/50 bg-secondary/10 px-3 py-2">
                    <span className="block font-mono text-[10px] uppercase text-muted-foreground">Same tract</span>
                    <span className="font-mono text-lg font-medium text-cream">{featureInputs.same_tract_properties}</span>
                  </div>
                )}
                {featureInputs.owner_links != null && (
                  <div className="rounded-lg border border-border/50 bg-secondary/10 px-3 py-2">
                    <span className="block font-mono text-[10px] uppercase text-muted-foreground">Owner links</span>
                    <span className="font-mono text-lg font-medium text-cream">{featureInputs.owner_links}</span>
                  </div>
                )}
                {featureInputs.violation_links != null && (
                  <div className="rounded-lg border border-border/50 bg-secondary/10 px-3 py-2">
                    <span className="block font-mono text-[10px] uppercase text-muted-foreground">Violation types</span>
                    <span className="font-mono text-lg font-medium text-cream">{featureInputs.violation_links}</span>
                  </div>
                )}
                {featureInputs.anomaly_raw != null && (
                  <div className="col-span-2 rounded-lg border border-border/50 bg-secondary/10 px-3 py-2 sm:col-span-4">
                    <span className="block font-mono text-[10px] uppercase text-muted-foreground">Raw anomaly (higher = more typical)</span>
                    <span className="font-mono text-lg font-medium text-cream">{featureInputs.anomaly_raw.toFixed(4)}</span>
                    <p className="mt-1 font-sans text-xs text-muted-foreground">
                      Negative values = property behaves atypically vs. the rest of the graph
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Why it matters */}
      <div className="glass-card rounded-xl p-6">
        <h3 className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
          Why this matters
        </h3>
        <p className="mb-4 font-sans text-sm leading-relaxed text-cream/80">
          Traditional title checks look at one property in isolation. Network Intelligence
          reveals risk that spreads through connections: shared owners, nearby comps, and
          correlated violations. A property can look clean on paper but sit in a cluster
          of high-turnover, violation-heavy buildings — or it can be an outlier in a
          stable neighborhood.
        </p>
        <ul className="space-y-2 font-sans text-sm leading-relaxed text-cream/70">
          <li className="flex items-start gap-2">
            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-teal/60" />
            <span><strong className="text-cream/90">Shared ownership:</strong> One owner controlling multiple properties can concentrate risk.</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-teal/60" />
            <span><strong className="text-cream/90">Block-level patterns:</strong> Comps and neighbors in the same block influence how “normal” this property looks.</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-teal/60" />
            <span><strong className="text-cream/90">Violations:</strong> DOB/HPD violations in the graph raise the anomaly score — you want to know if this property clusters with problem buildings.</span>
          </li>
        </ul>
      </div>
    </div>
  )
}
