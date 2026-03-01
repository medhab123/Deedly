'use client'

import { useState, useRef, useCallback } from 'react'
import { HeroSlide } from '@/components/landing/hero-slide'
import { InsightSlide } from '@/components/landing/insight-slide'
import { AddressInputSlide } from '@/components/landing/address-input-slide'
import { Dashboard } from '@/components/dashboard/dashboard'
import { useAnalysis } from '@/lib/store'
import type { BuyerPersona, AnalysisResult } from '@/lib/types'
import { toast } from 'sonner'

export default function Home() {
  const [view, setView] = useState<'landing' | 'dashboard'>('landing')
  const scrollRef = useRef<HTMLDivElement>(null)
  const { mutate } = useAnalysis()

  const scrollToSlide = useCallback((index: number) => {
    const container = scrollRef.current
    if (!container) return
    const slides = container.querySelectorAll('.snap-slide')
    slides[index]?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  const handleAnalyze = useCallback(
    async (address: string, persona: BuyerPersona) => {
      try {
        const res = await fetch('/api/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ address, persona }),
        })
        if (!res.ok) throw new Error('Failed')
        const data: AnalysisResult = await res.json()
        mutate(data, false)
        setView('dashboard')
      } catch {
        toast.error('Analysis failed. Check that the backend is running and try again.')
      }
    },
    [mutate]
  )

  const handleBackToLanding = useCallback(() => {
    mutate(undefined, false)
    setView('landing')
  }, [mutate])

  if (view === 'dashboard') {
    return <Dashboard onBack={handleBackToLanding} />
  }

  return (
    <div ref={scrollRef} className="snap-container">
      <HeroSlide onNext={() => scrollToSlide(1)} />
      <InsightSlide />
      <AddressInputSlide onAnalyze={handleAnalyze} />
    </div>
  )
}
