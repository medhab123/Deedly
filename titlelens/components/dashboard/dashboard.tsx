'use client'

import { useAnalysis } from '@/lib/store'
import { LeftPanel } from './left-panel'
import { OverviewTab } from './tabs/overview-tab'
import { TitleHealthTab } from './tabs/title-health-tab'
import { NetworkIntelligenceTab } from './tabs/network-intelligence-tab'
import { PersonaTab } from './tabs/persona-tab'
import { CopilotTab } from './tabs/copilot-tab'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { BarChart3, Shield, Network, User, MessageSquare, Menu, X } from 'lucide-react'
import { useState } from 'react'

export function Dashboard({ onBack }: { onBack: () => void }) {
  const { analysis } = useAnalysis()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  if (!analysis) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="font-mono text-sm text-muted-foreground">No analysis data. Return to analyze a property.</p>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen bg-background animate-fade-lift-in">
      {/* Left Panel - Desktop */}
      <div className="hidden lg:flex lg:w-80 lg:shrink-0 lg:flex-col border-r border-border bg-card sticky top-0 h-screen">
        <LeftPanel analysis={analysis} onBack={onBack} />
      </div>

      {/* Mobile header */}
      <div className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between border-b border-border bg-card/95 backdrop-blur-md px-4 py-3 lg:hidden">
        <div className="flex flex-col">
          <span className="font-serif text-sm text-cream">Deedly</span>
          <span className="font-mono text-[10px] text-muted-foreground truncate max-w-48">{analysis.address}</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <div
              className="size-2 rounded-full"
              style={{
                background: analysis.deedlyScore >= 70
                  ? 'var(--teal)'
                  : analysis.deedlyScore >= 45
                  ? 'var(--amber)'
                  : 'var(--destructive)',
              }}
            />
            <span className="font-mono text-xs text-cream">{analysis.deedlyScore}</span>
          </div>
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="rounded-lg border border-border p-1.5 text-muted-foreground hover:text-cream"
            aria-label="Toggle menu"
          >
            {mobileMenuOpen ? <X className="size-4" /> : <Menu className="size-4" />}
          </button>
        </div>
      </div>

      {/* Mobile drawer */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setMobileMenuOpen(false)} />
          <div className="absolute left-0 top-0 bottom-0 w-80 bg-card border-r border-border overflow-y-auto">
            <LeftPanel analysis={analysis} onBack={onBack} />
          </div>
        </div>
      )}

      {/* Right Panel */}
      <main className="flex-1 overflow-y-auto pt-14 lg:pt-0">
        <Tabs defaultValue="overview" className="h-full">
          <div className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur-md px-6 pt-6 lg:pt-8">
            {/* Header */}
            <div className="mb-4 flex items-center justify-between">
              <h1 className="font-serif text-2xl text-cream lg:text-3xl">Analysis Results</h1>
              <span className="hidden font-mono text-xs text-muted-foreground sm:block">
                ID: {analysis.id}
              </span>
            </div>

            <TabsList className="w-full justify-start bg-transparent gap-1 p-0 h-auto border-b-0">
              <TabsTrigger
                value="overview"
                className="rounded-none border-b-2 border-transparent bg-transparent px-4 py-2.5 font-mono text-xs data-[state=active]:border-teal data-[state=active]:bg-transparent data-[state=active]:text-teal data-[state=active]:shadow-none text-muted-foreground hover:text-cream"
              >
                <BarChart3 className="size-3.5" />
                Overview
              </TabsTrigger>
              <TabsTrigger
                value="title"
                className="rounded-none border-b-2 border-transparent bg-transparent px-4 py-2.5 font-mono text-xs data-[state=active]:border-teal data-[state=active]:bg-transparent data-[state=active]:text-teal data-[state=active]:shadow-none text-muted-foreground hover:text-cream"
              >
                <Shield className="size-3.5" />
                Title Health
              </TabsTrigger>
              <TabsTrigger
                value="network"
                className="rounded-none border-b-2 border-transparent bg-transparent px-4 py-2.5 font-mono text-xs data-[state=active]:border-teal data-[state=active]:bg-transparent data-[state=active]:text-teal data-[state=active]:shadow-none text-muted-foreground hover:text-cream"
              >
                <Network className="size-3.5" />
                Network Intelligence
              </TabsTrigger>
              <TabsTrigger
                value="persona"
                className="rounded-none border-b-2 border-transparent bg-transparent px-4 py-2.5 font-mono text-xs data-[state=active]:border-teal data-[state=active]:bg-transparent data-[state=active]:text-teal data-[state=active]:shadow-none text-muted-foreground hover:text-cream"
              >
                <User className="size-3.5" />
                Persona
              </TabsTrigger>
              <TabsTrigger
                value="copilot"
                className="rounded-none border-b-2 border-transparent bg-transparent px-4 py-2.5 font-mono text-xs data-[state=active]:border-teal data-[state=active]:bg-transparent data-[state=active]:text-teal data-[state=active]:shadow-none text-muted-foreground hover:text-cream"
              >
                <MessageSquare className="size-3.5" />
                Copilot
              </TabsTrigger>
            </TabsList>
          </div>

          <div className="p-6">
            <TabsContent value="overview">
              <OverviewTab analysis={analysis} />
            </TabsContent>
            <TabsContent value="title">
              <TitleHealthTab analysis={analysis} />
            </TabsContent>
            <TabsContent value="network">
              <NetworkIntelligenceTab analysis={analysis} />
            </TabsContent>
            <TabsContent value="persona">
              <PersonaTab analysis={analysis} />
            </TabsContent>
            <TabsContent value="copilot">
              <CopilotTab analysisId={analysis.id} />
            </TabsContent>
          </div>
        </Tabs>
      </main>
    </div>
  )
}
