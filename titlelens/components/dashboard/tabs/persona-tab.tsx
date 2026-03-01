'use client'

import type { AnalysisResult } from '@/lib/types'
import { CheckCircle2, AlertTriangle, User, Briefcase, Home, Wifi } from 'lucide-react'

const PERSONA_CONFIG: Record<string, { icon: React.ReactNode; title: string; description: string }> = {
  family: {
    icon: <Home className="size-5 text-teal" />,
    title: 'Family Buyer',
    description: 'Focused on schools, safety, stability, and long-term livability.',
  },
  investor: {
    icon: <Briefcase className="size-5 text-teal" />,
    title: 'Investor',
    description: 'Focused on turnover patterns, appreciation signals, rental demand, and network risk.',
  },
  'first-time': {
    icon: <User className="size-5 text-teal" />,
    title: 'First-Time Buyer',
    description: 'Top risks explained plainly, with affordability notes and questions to ask your agent.',
  },
  'remote-worker': {
    icon: <Wifi className="size-5 text-teal" />,
    title: 'Remote Worker',
    description: 'Amenities, noise levels, connectivity, and commute signals for distributed living.',
  },
}

export function PersonaTab({ analysis }: { analysis: AnalysisResult }) {
  const config = PERSONA_CONFIG[analysis.persona] || PERSONA_CONFIG.family

  return (
    <div className="flex flex-col gap-6 animate-fade-lift-in">
      {/* Persona header */}
      <div className="glass-card rounded-xl p-6">
        <div className="flex items-center gap-3">
          {config.icon}
          <div>
            <h3 className="font-serif text-xl text-cream">{config.title}</h3>
            <p className="font-sans text-sm text-muted-foreground">{config.description}</p>
          </div>
        </div>
      </div>

      {/* Two-column pros and watch-outs */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Pros */}
        <div className="glass-card rounded-xl p-6">
          <h3 className="mb-4 flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-teal">
            <CheckCircle2 className="size-3.5" />
            Personalized Pros
          </h3>
          <div className="flex flex-col gap-3">
            {analysis.personaPros.map((pro, i) => (
              <div key={i} className="flex flex-col gap-0.5 rounded-lg bg-teal/5 border border-teal/10 p-3">
                <span className="font-mono text-xs font-medium text-teal">{pro.label}</span>
                <span className="font-sans text-sm text-cream/80 leading-relaxed">{pro.value}</span>
              </div>
            ))}
            {analysis.personaPros.length === 0 && (
              <p className="font-mono text-xs text-muted-foreground">No specific pros identified for this persona.</p>
            )}
          </div>
        </div>

        {/* Watch-outs */}
        <div className="glass-card rounded-xl p-6">
          <h3 className="mb-4 flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-amber">
            <AlertTriangle className="size-3.5" />
            Watch-Outs
          </h3>
          <div className="flex flex-col gap-3">
            {analysis.personaWatchOuts.map((wo, i) => (
              <div key={i} className="flex flex-col gap-0.5 rounded-lg bg-amber/5 border border-amber/10 p-3">
                <span className="font-mono text-xs font-medium text-amber">{wo.label}</span>
                <span className="font-sans text-sm text-cream/80 leading-relaxed">{wo.value}</span>
              </div>
            ))}
            {analysis.personaWatchOuts.length === 0 && (
              <p className="font-mono text-xs text-muted-foreground">No specific watch-outs identified for this persona.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
