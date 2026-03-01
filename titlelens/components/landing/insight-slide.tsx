'use client'

import { useEffect, useRef, useState } from 'react'

/** Round to fixed decimals for hydration-safe output (server/client must match) */
function round4(n: number) {
  return Math.round(n * 1e4) / 1e4
}

const RISK_NODES = [
  { label: 'Crime Clusters', angle: 0 },
  { label: 'Liens', angle: 60 },
  { label: 'Turnover', angle: 120 },
  { label: 'Flood Zones', angle: 180 },
  { label: 'Network Flags', angle: 240 },
  { label: 'Easements', angle: 300 },
]

export function InsightSlide() {
  const [visible, setVisible] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setVisible(true)
      },
      { threshold: 0.5 }
    )
    if (ref.current) observer.observe(ref.current)
    return () => observer.disconnect()
  }, [])

  return (
    <section ref={ref} className="snap-slide relative flex items-center overflow-hidden">
      <div className="mx-auto flex w-full max-w-7xl flex-col items-center gap-16 px-6 lg:flex-row lg:gap-20">
        {/* Left: Pull quote */}
        <div className="flex-1">
          <blockquote className="font-serif text-3xl leading-snug text-cream md:text-4xl lg:text-5xl text-balance">
            {'"Most tools ask:'}
            <br />
            <span className="text-amber">Is this property bad?</span>
            <br />
            {'We ask:'}
            <br />
            <span className="text-teal">{"Who does it hang out with?"}</span>
            {'"'}
          </blockquote>
          <p className="mt-8 max-w-md font-sans text-lg leading-relaxed text-muted-foreground">
            Deedly maps the neighborhood of risk — not just the address.
          </p>
        </div>

        {/* Right: Animated diagram */}
        <div className="relative flex flex-1 items-center justify-center">
          <div className="relative size-72 md:size-80 lg:size-96">
            {/* Center house node */}
            <div
              className={`absolute left-1/2 top-1/2 z-10 flex size-16 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-teal/40 bg-teal/10 transition-all duration-1000 ${
                visible ? 'scale-100 opacity-100' : 'scale-50 opacity-0'
              }`}
            >
              <svg className="size-7 text-teal" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M3 9.5L12 3l9 6.5V20a1 1 0 01-1 1H4a1 1 0 01-1-1V9.5z" />
                <path d="M9 21V12h6v9" />
              </svg>
            </div>

            {/* Risk nodes */}
            {RISK_NODES.map((node, i) => {
              const radian = (node.angle * Math.PI) / 180
              const radius = 42 // percentage from center
              const x = round4(50 + radius * Math.cos(radian))
              const y = round4(50 + radius * Math.sin(radian))
              const delay = round4(i * 0.15 + 0.3)

              return (
                <div key={node.label}>
                  {/* Connection line */}
                  <svg
                    className="absolute inset-0 size-full"
                    viewBox="0 0 100 100"
                    style={{
                      transition: `opacity 0.8s ease ${delay}s`,
                      opacity: visible ? 0.3 : 0,
                    }}
                  >
                    <line
                      x1="50"
                      y1="50"
                      x2={x}
                      y2={y}
                      stroke="#785D32"
                      strokeWidth="0.3"
                      strokeDasharray="2 2"
                    />
                  </svg>
                  {/* Node */}
                  <div
                    className="absolute flex flex-col items-center gap-1"
                    style={{
                      left: `${x}%`,
                      top: `${y}%`,
                      transform: 'translate(-50%, -50%)',
                      transition: `all 0.6s ease ${delay}s`,
                      opacity: visible ? 1 : 0,
                      scale: visible ? 1 : 0.5,
                    }}
                  >
                    <div className="size-3 rounded-full bg-amber/60 animate-node-pulse" style={{ animationDelay: `${round4(i * 0.4)}s` }} />
                    <span className="whitespace-nowrap font-mono text-[10px] text-muted-foreground md:text-xs">
                      {node.label}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </section>
  )
}
