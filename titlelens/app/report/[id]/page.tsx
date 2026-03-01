'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import type { AnalysisResult } from '@/lib/types'
import { Printer, AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'

function getSignalIcon(type: string) {
  switch (type) {
    case 'success': return <CheckCircle2 className="size-3 text-teal" />
    case 'warning': return <AlertTriangle className="size-3 text-amber" />
    case 'danger': return <XCircle className="size-3 text-destructive" />
    default: return <Info className="size-3 text-muted-foreground" />
  }
}

export default function ReportPage() {
  const params = useParams()
  const [report, setReport] = useState<AnalysisResult | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchReport() {
      try {
        const res = await fetch(`/api/report/${params.id}`)
        if (res.ok) {
          const data = await res.json()
          setReport(data)
        }
      } catch {
        // Failed to load
      } finally {
        setLoading(false)
      }
    }
    fetchReport()
  }, [params.id])

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="font-mono text-sm text-muted-foreground">Loading report...</p>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="font-mono text-sm text-muted-foreground">Report not found.</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-cream text-obsidian print:bg-white">
      {/* Print header bar */}
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-obsidian/10 bg-cream px-6 py-3 print:hidden">
        <span className="font-serif text-lg text-obsidian">Deedly Report</span>
        <button
          onClick={() => window.print()}
          className="flex items-center gap-2 rounded-lg bg-obsidian px-4 py-2 font-mono text-xs text-cream transition-colors hover:bg-obsidian/90"
        >
          <Printer className="size-3.5" />
          Print / Save as PDF
        </button>
      </div>

      {/* Report content */}
      <div className="mx-auto max-w-3xl px-8 py-12">
        {/* Header */}
        <div className="mb-8 border-b border-obsidian/10 pb-6">
          <h1 className="font-serif text-3xl text-obsidian">Deedly Property Analysis</h1>
          <p className="mt-2 font-mono text-xs text-obsidian/60">
            Report generated {new Date(report.timestamp).toLocaleString()} | ID: {report.id}
          </p>
          <p className="mt-3 font-sans text-base text-obsidian/80">{report.address}</p>
        </div>

        {/* Score + Verdict */}
        <section className="mb-8">
          <h2 className="mb-3 font-serif text-xl text-obsidian">Score & Verdict</h2>
          <div className="flex items-center gap-6 rounded-lg border border-obsidian/10 bg-obsidian/5 p-4">
            <div className="flex flex-col items-center">
              <span className="font-serif text-4xl text-obsidian">{report.deedlyScore}</span>
              <span className="font-mono text-[10px] uppercase text-obsidian/50">/ 100</span>
            </div>
            <div className="flex-1">
              <p className="font-sans text-sm text-obsidian/80 leading-relaxed">{report.verdict}</p>
            </div>
          </div>
        </section>

        {/* Title Health */}
        <section className="mb-8">
          <h2 className="mb-3 font-serif text-xl text-obsidian">Title Health</h2>
          <div className="rounded-lg border border-obsidian/10 p-4">
            <div className="grid gap-3">
              <div>
                <span className="font-mono text-xs text-obsidian/50">Ownership Turnover</span>
                <p className="font-sans text-sm text-obsidian/80">{report.titleHealth.ownershipTurnoverFrequency}</p>
              </div>
              <div>
                <span className="font-mono text-xs text-obsidian/50">Zoning</span>
                <p className="font-sans text-sm text-obsidian/80">{report.titleHealth.zoningStability}</p>
              </div>
              <div>
                <span className="font-mono text-xs text-obsidian/50">Claim Likelihood</span>
                <p className="font-sans text-sm text-obsidian/80">{report.titleHealth.estimatedClaimLikelihood}%</p>
              </div>
            </div>
          </div>
        </section>

        {/* Top Signals */}
        <section className="mb-8">
          <h2 className="mb-3 font-serif text-xl text-obsidian">Top Signals</h2>
          <div className="flex flex-wrap gap-2">
            {report.signals.map((s) => (
              <span key={s.label} className="inline-flex items-center gap-1.5 rounded-full border border-obsidian/10 px-3 py-1 font-mono text-xs text-obsidian/80">
                {getSignalIcon(s.type)}
                {s.label}
              </span>
            ))}
          </div>
        </section>

        {/* Network Risk Summary */}
        <section className="mb-8">
          <h2 className="mb-3 font-serif text-xl text-obsidian">Network Risk Summary</h2>
          <div className="rounded-lg border border-obsidian/10 p-4">
            <p className="font-sans text-sm text-obsidian/80 leading-relaxed">
              {report.networkRisk.interpretation}
            </p>
            <div className="mt-3 grid grid-cols-3 gap-3">
              <div>
                <span className="font-mono text-[10px] text-obsidian/50 uppercase">Score</span>
                <p className="font-serif text-lg text-obsidian">{report.networkRisk.score}</p>
              </div>
              <div>
                <span className="font-mono text-[10px] text-obsidian/50 uppercase">Owner Properties</span>
                <p className="font-serif text-lg text-obsidian">{report.networkRisk.ownerDegree}</p>
              </div>
              <div>
                <span className="font-mono text-[10px] text-obsidian/50 uppercase">Flagged</span>
                <p className="font-serif text-lg text-obsidian">{report.networkRisk.connectedFlaggedProperties}</p>
              </div>
            </div>
          </div>
        </section>

        {/* Persona Recommendations */}
        <section className="mb-8">
          <h2 className="mb-3 font-serif text-xl text-obsidian">Persona Recommendations</h2>
          <div className="grid gap-3 md:grid-cols-2">
            {report.personaPros.map((p, i) => (
              <div key={i} className="rounded-lg border border-teal/20 bg-teal/5 p-3">
                <span className="font-mono text-[10px] uppercase text-teal">Pro</span>
                <p className="font-mono text-xs font-medium text-obsidian">{p.label}</p>
                <p className="font-sans text-xs text-obsidian/70">{p.value}</p>
              </div>
            ))}
            {report.personaWatchOuts.map((w, i) => (
              <div key={i} className="rounded-lg border border-amber/20 bg-amber/5 p-3">
                <span className="font-mono text-[10px] uppercase text-amber">Watch-Out</span>
                <p className="font-mono text-xs font-medium text-obsidian">{w.label}</p>
                <p className="font-sans text-xs text-obsidian/70">{w.value}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Disclaimer */}
        <section className="border-t border-obsidian/10 pt-6">
          <p className="font-mono text-[10px] leading-relaxed text-obsidian/40">
            DISCLAIMER: This report is generated using publicly available data and proprietary risk modeling.
            It is not a substitute for professional legal, financial, or real estate advice. Deedly makes
            no warranties regarding the accuracy or completeness of this analysis. The network risk score
            is based on relationship pattern analysis and should be considered alongside traditional due
            diligence methods. Always consult with qualified professionals before making real estate
            decisions. Estimated claim likelihoods are statistical approximations and do not constitute
            guarantees or predictions.
          </p>
        </section>
      </div>
    </div>
  )
}
