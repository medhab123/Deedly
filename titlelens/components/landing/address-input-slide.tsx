'use client'

import { useState, useCallback } from 'react'
import { ProgressTicker } from './progress-ticker'
import { toast } from 'sonner'
import type { BuyerPersona } from '@/lib/types'

const PERSONA_OPTIONS: { value: BuyerPersona; label: string }[] = [
  { value: 'family', label: 'Family' },
  { value: 'investor', label: 'Investor' },
  { value: 'first-time', label: 'First-Time Buyer' },
  { value: 'remote-worker', label: 'Remote Worker' },
]

const DEMO_ADDRESSES = [
  '742 Evergreen Terrace, Springfield, IL 62704',
  '1313 Mockingbird Lane, Gatlin, NE 68001',
]

interface AddressInputSlideProps {
  onAnalyze: (address: string, persona: BuyerPersona) => Promise<void>
}

export function AddressInputSlide({ onAnalyze }: AddressInputSlideProps) {
  const [address, setAddress] = useState('')
  const [persona, setPersona] = useState<BuyerPersona>('family')
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = useCallback(async () => {
    if (!address.trim()) {
      toast.error('Please enter an address')
      return
    }
    setIsLoading(true)
    try {
      await onAnalyze(address, persona)
    } catch {
      toast.error('Analysis unavailable — loading demo data')
      setIsLoading(false)
    }
  }, [address, persona, onAnalyze])

  const handleDemo = useCallback(() => {
    const demoAddr = DEMO_ADDRESSES[Math.floor(Math.random() * DEMO_ADDRESSES.length)]
    setAddress(demoAddr)
  }, [])

  const handleReset = useCallback(() => {
    setAddress('')
    setPersona('family')
    setIsLoading(false)
  }, [])

  if (isLoading) {
    return (
      <section className="snap-slide flex items-center justify-center">
        <ProgressTicker onComplete={() => {}} />
      </section>
    )
  }

  return (
    <section className="snap-slide flex items-center justify-center px-6">
      <div className="glass-card w-full max-w-lg rounded-2xl p-8 md:p-10">
        {/* Header */}
        <div className="mb-8 text-center">
          <h2 className="font-serif text-3xl text-cream md:text-4xl">
            Analyze a Property
          </h2>
          <p className="mt-2 font-sans text-sm text-muted-foreground">
            Enter any address to uncover hidden risk signals
          </p>
        </div>

        {/* Address input */}
        <div className="flex flex-col gap-6">
          <div>
            <label htmlFor="address-input" className="sr-only">Property Address</label>
            <input
              id="address-input"
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
              placeholder="Enter a property address..."
              className="w-full rounded-lg border border-border bg-secondary/50 px-4 py-3.5 font-mono text-sm text-cream placeholder:text-muted-foreground focus:border-teal focus:outline-none focus:ring-1 focus:ring-teal transition-colors"
            />
          </div>

          {/* Buyer type selector */}
          <div>
            <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
              Buyer Type
            </p>
            <div className="flex flex-wrap gap-2">
              {PERSONA_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setPersona(opt.value)}
                  className={`rounded-full px-4 py-2 font-mono text-xs transition-all duration-200 ${
                    persona === opt.value
                      ? 'border border-teal bg-teal/15 text-teal'
                      : 'border border-border bg-secondary/30 text-muted-foreground hover:border-teal/30 hover:text-cream'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Buttons */}
          <div className="flex flex-col gap-3">
            <button
              onClick={handleSubmit}
              className="rounded-lg bg-teal px-6 py-3.5 font-mono text-sm font-medium text-primary-foreground transition-all duration-200 hover:bg-teal/90 glow-border"
            >
              {"Analyze Property"}
            </button>
            <div className="flex gap-3">
              <button
                onClick={handleDemo}
                className="flex-1 rounded-lg border border-border bg-transparent px-4 py-2.5 font-mono text-xs text-muted-foreground transition-colors hover:border-teal/30 hover:text-cream"
              >
                Try a Demo Address
              </button>
              <button
                onClick={handleReset}
                className="flex-1 rounded-lg border border-border bg-transparent px-4 py-2.5 font-mono text-xs text-muted-foreground transition-colors hover:border-border hover:text-cream"
              >
                Reset
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
