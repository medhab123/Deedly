'use client'

import { NetworkGraph } from '@/components/network-graph'
import { ChevronDown } from 'lucide-react'

export function HeroSlide({ onNext }: { onNext: () => void }) {
  return (
    <section className="snap-slide relative flex flex-col items-center justify-center overflow-hidden">
      {/* Network graph background */}
      <div className="absolute inset-0 opacity-40">
        <NetworkGraph className="absolute inset-0" />
      </div>

      {/* Radial gradient overlay */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_0%,var(--obsidian)_70%)]" />

      {/* Content */}
      <div className="relative z-10 flex flex-col items-center gap-8 px-6 text-center">
        <p className="font-mono text-sm tracking-[0.3em] uppercase text-teal opacity-80">
          Buyer Confidence Platform
        </p>

        <h1 className="font-serif text-5xl leading-tight text-cream md:text-7xl lg:text-8xl text-balance">
          {"Risk isn't a property."}
          <br />
          {"It's a network."}
        </h1>

        <p className="max-w-2xl font-sans text-lg leading-relaxed text-muted-foreground md:text-xl">
          Deedly sees what other tools miss — the relationships, patterns, and
          signals hiding in plain sight around every address.
        </p>

        <button
          onClick={onNext}
          className="mt-4 rounded-lg border border-teal/30 bg-teal/10 px-8 py-3 font-mono text-sm font-medium text-teal transition-all duration-300 hover:bg-teal/20 hover:border-teal/50 glow-border"
        >
          {"Analyze a Property \u2192"}
        </button>
      </div>

      {/* Scroll indicator */}
      <button
        onClick={onNext}
        className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-muted-foreground opacity-60 transition-opacity hover:opacity-100"
        aria-label="Scroll down"
      >
        <span className="font-mono text-xs tracking-widest uppercase">Scroll</span>
        <ChevronDown className="size-4 animate-bounce" />
      </button>
    </section>
  )
}
