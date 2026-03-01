'use client'

import { ScoreGauge } from './score-gauge'
import { Badge } from '@/components/ui/badge'
import { Copy, FileText, Download, ArrowLeft, MapPin } from 'lucide-react'
import { toast } from 'sonner'
import type { AnalysisResult } from '@/lib/types'

const PERSONA_LABELS: Record<string, string> = {
  family: 'Family',
  investor: 'Investor',
  'first-time': 'First-Time Buyer',
  'remote-worker': 'Remote Worker',
}

function getRiskColor(level: string) {
  switch (level) {
    case 'LOW': return 'bg-teal/15 text-teal border-teal/30'
    case 'MED': return 'bg-amber/15 text-amber border-amber/30'
    case 'HIGH': return 'bg-destructive/15 text-destructive border-destructive/30'
    default: return ''
  }
}

export function LeftPanel({ analysis, onBack }: { analysis: AnalysisResult; onBack: () => void }) {
  const handleCopyLink = () => {
    const url = `${window.location.origin}?id=${analysis.id}`
    navigator.clipboard.writeText(url)
    toast.success('Link copied to clipboard')
  }

  const handleDownloadJSON = () => {
    const blob = new Blob([JSON.stringify(analysis, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `deedly-${analysis.id}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <aside className="flex h-full flex-col gap-6 overflow-y-auto p-6">
      {/* Back button */}
      <button
        onClick={onBack}
        className="flex items-center gap-2 font-mono text-xs text-muted-foreground transition-colors hover:text-cream self-start"
      >
        <ArrowLeft className="size-3.5" />
        New Analysis
      </button>

      {/* Address */}
      <div className="flex flex-col gap-1">
        <div className="flex items-start gap-2">
          <MapPin className="mt-0.5 size-4 shrink-0 text-teal" />
          <div>
            <p className="font-sans text-sm font-medium text-cream leading-snug">{analysis.address}</p>
            <p className="mt-1 font-mono text-xs text-muted-foreground">
              {PERSONA_LABELS[analysis.persona]}
            </p>
          </div>
        </div>
      </div>

      {/* Divider */}
      <div className="h-px bg-border" />

      {/* Score */}
      <div className="flex flex-col items-center">
        <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
          Deedly Score
        </p>
        <ScoreGauge score={analysis.deedlyScore} />
      </div>

      {/* Verdict */}
      <div className="min-w-0">
        <p className="font-sans text-sm leading-relaxed text-cream/90 text-center break-words">
          {analysis.verdict}
        </p>
      </div>

      {/* Title Health Badge */}
      <div className="flex items-center justify-center">
        <span className={`inline-flex items-center rounded-full border px-3 py-1 font-mono text-xs font-medium ${getRiskColor(analysis.titleRiskLevel)}`}>
          Title Health: {analysis.titleRiskLevel} RISK
        </span>
      </div>

      {/* Divider */}
      <div className="h-px bg-border" />

      {/* Actions */}
      <div className="flex flex-col gap-2">
        <a
          href={`/report/${analysis.id}`}
          className="flex items-center justify-center gap-2 rounded-lg border border-border bg-secondary/30 px-4 py-2.5 font-mono text-xs text-cream transition-colors hover:bg-secondary/50"
        >
          <FileText className="size-3.5" />
          Open Report
        </a>
        <div className="flex gap-2">
          <button
            onClick={handleCopyLink}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-border bg-secondary/30 px-3 py-2 font-mono text-xs text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-cream"
          >
            <Copy className="size-3" />
            Copy Link
          </button>
          <button
            onClick={handleDownloadJSON}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-border bg-secondary/30 px-3 py-2 font-mono text-xs text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-cream"
          >
            <Download className="size-3" />
            JSON
          </button>
        </div>
      </div>

      {/* Timestamp */}
      <p className="mt-auto font-mono text-[10px] text-muted-foreground/60 text-center">
        Analyzed {new Date(analysis.timestamp).toLocaleString()}
      </p>
    </aside>
  )
}
