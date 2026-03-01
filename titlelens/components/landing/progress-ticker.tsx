'use client'

import { useEffect, useState } from 'react'
import { LOADING_STEPS } from '@/lib/demo-data'
import { Check, Loader2 } from 'lucide-react'

export function ProgressTicker({ onComplete }: { onComplete: () => void }) {
  const [currentStep, setCurrentStep] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentStep((prev) => {
        if (prev >= LOADING_STEPS.length - 1) {
          clearInterval(interval)
          setTimeout(onComplete, 600)
          return prev
        }
        return prev + 1
      })
    }, 500)
    return () => clearInterval(interval)
  }, [onComplete])

  return (
    <div className="flex flex-col items-center gap-8">
      <div className="flex flex-col items-center gap-3">
        <div className="size-12 rounded-full border border-teal/30 bg-teal/5 flex items-center justify-center">
          <Loader2 className="size-5 text-teal animate-spin" />
        </div>
        <p className="font-serif text-2xl text-cream">Analyzing Property</p>
      </div>
      
      <div className="w-full max-w-sm flex flex-col gap-2">
        {LOADING_STEPS.map((step, i) => (
          <div
            key={step}
            className="flex items-center gap-3 transition-all duration-300"
            style={{
              opacity: i <= currentStep ? 1 : 0.3,
              transform: i <= currentStep ? 'translateX(0)' : 'translateX(-8px)',
              transitionDelay: `${i * 50}ms`,
            }}
          >
            <div className="flex size-5 shrink-0 items-center justify-center">
              {i < currentStep ? (
                <Check className="size-4 text-teal" />
              ) : i === currentStep ? (
                <div className="size-2 rounded-full bg-teal animate-pulse" />
              ) : (
                <div className="size-1.5 rounded-full bg-muted-foreground/30" />
              )}
            </div>
            <span className={`font-mono text-sm ${i <= currentStep ? 'text-cream' : 'text-muted-foreground'}`}>
              {step}
              {i === currentStep && (
                <span className="inline-block animate-pulse">...</span>
              )}
            </span>
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <div className="w-full max-w-sm h-0.5 rounded-full bg-secondary overflow-hidden">
        <div
          className="h-full bg-teal rounded-full transition-all duration-500"
          style={{ width: `${((currentStep + 1) / LOADING_STEPS.length) * 100}%` }}
        />
      </div>
    </div>
  )
}
