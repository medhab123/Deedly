'use client'

import type { AnalysisResult } from '@/lib/types'
import { AlertTriangle, Info, CheckCircle2, XCircle } from 'lucide-react'

function getBarColor(value: number): string {
  if (value >= 70) return 'bg-teal'
  if (value >= 45) return 'bg-amber'
  return 'bg-destructive'
}

function getSignalStyle(type: string) {
  switch (type) {
    case 'success':
      return 'border-teal/30 bg-teal/10 text-teal'
    case 'warning':
      return 'border-amber/30 bg-amber/10 text-amber'
    case 'danger':
      return 'border-destructive/30 bg-destructive/10 text-destructive'
    default:
      return 'border-border bg-secondary/30 text-muted-foreground'
  }
}

function getSignalIcon(type: string) {
  switch (type) {
    case 'success': return <CheckCircle2 className="size-3" />
    case 'warning': return <AlertTriangle className="size-3" />
    case 'danger': return <XCircle className="size-3" />
    default: return <Info className="size-3" />
  }
}

function AnimatedBar({ label, value, delay }: { label: string; value: number; delay: number }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs text-cream">{label}</span>
        <span className="font-mono text-xs text-muted-foreground">{value}/100</span>
      </div>
      <div className="h-2 w-full rounded-full bg-secondary overflow-hidden">
        <div
          className={`h-full rounded-full ${getBarColor(value)} transition-all duration-1000 ease-out`}
          style={{
            width: `${value}%`,
            transitionDelay: `${delay}ms`,
          }}
        />
      </div>
    </div>
  )
}

export function OverviewTab({ analysis }: { analysis: AnalysisResult }) {
  return (
    <div className="flex flex-col gap-6 animate-fade-lift-in">
      {/* Risk bars */}
      <div className="glass-card rounded-xl p-6">
        <h3 className="mb-4 font-mono text-xs uppercase tracking-widest text-muted-foreground">
          Risk Dimensions
        </h3>
        <div className="flex flex-col gap-4">
          <AnimatedBar label="Safety" value={analysis.riskScores.safety} delay={0} />
          <AnimatedBar label="Title Health" value={analysis.riskScores.titleHealth} delay={100} />
          <AnimatedBar label="Environmental Risk" value={analysis.riskScores.environmentalRisk} delay={200} />
          <AnimatedBar label="Neighborhood Stability" value={analysis.riskScores.neighborhoodStability} delay={300} />
        </div>
      </div>

      {/* Key Signals */}
      <div className="glass-card rounded-xl p-6">
        <h3 className="mb-4 font-mono text-xs uppercase tracking-widest text-muted-foreground">
          Key Signals
        </h3>
        <div className="flex flex-wrap gap-2">
          {analysis.signals.map((signal) => (
            <span
              key={signal.label}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-xs ${getSignalStyle(signal.type)}`}
            >
              {getSignalIcon(signal.type)}
              {signal.label}
            </span>
          ))}
        </div>
      </div>

      {/* Analysis Summary */}
      <div className="glass-card rounded-xl p-6 min-w-0">
        <h3 className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
          Analysis Summary
        </h3>
        <blockquote className="border-l-2 border-teal/40 pl-4 font-sans text-sm leading-relaxed text-cream/90 italic break-words whitespace-pre-wrap">
          {analysis.aiSummary}
        </blockquote>
      </div>
    </div>
  )
}
