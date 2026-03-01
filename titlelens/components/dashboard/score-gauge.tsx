'use client'

import { useEffect, useState } from 'react'

function getScoreColor(score: number): string {
  if (score >= 70) return '#785D32' // gold
  if (score >= 45) return '#9a7d4e' // amber-gold
  return '#3E160C' // rough
}

function getScoreLabel(score: number): string {
  if (score >= 70) return 'Low Risk'
  if (score >= 45) return 'Moderate Risk'
  return 'Elevated Risk'
}

export function ScoreGauge({ score }: { score: number }) {
  const [animatedScore, setAnimatedScore] = useState(0)
  const color = getScoreColor(score)
  const circumference = 2 * Math.PI * 45
  const offset = circumference - (animatedScore / 100) * circumference

  useEffect(() => {
    let frame: number
    const duration = 1500
    const start = performance.now()

    const animate = (now: number) => {
      const elapsed = now - start
      const progress = Math.min(elapsed / duration, 1)
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3)
      setAnimatedScore(Math.round(score * eased))
      if (progress < 1) {
        frame = requestAnimationFrame(animate)
      }
    }
    frame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frame)
  }, [score])

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative size-36">
        <svg className="size-full -rotate-90" viewBox="0 0 100 100">
          {/* Background circle */}
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke="var(--secondary)"
            strokeWidth="6"
          />
          {/* Score arc */}
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke={color}
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            style={{ transition: 'stroke-dashoffset 0.1s linear' }}
          />
        </svg>
        {/* Score number */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-serif text-4xl text-cream" style={{ color }}>
            {animatedScore}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            / 100
          </span>
        </div>
      </div>
      <span
        className="font-mono text-xs font-medium uppercase tracking-wider"
        style={{ color }}
      >
        {getScoreLabel(score)}
      </span>
    </div>
  )
}
