import { NextRequest, NextResponse } from 'next/server'

const getBackendUrl = () =>
  process.env.BACKEND_URL || process.env.NEXT_PUBLIC_DEEDLY_API || 'http://localhost:8000'

export async function POST(request: NextRequest) {
  const body = await request.json()
  const { analysisId, question } = body as { analysisId: string; question: string }

  if (!analysisId?.trim() || !question?.trim()) {
    return NextResponse.json({ error: 'analysisId and question required' }, { status: 400 })
  }

  const base = getBackendUrl().replace(/\/$/, '')

  try {
    const res = await fetch(`${base}/api/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ analysisId: analysisId.trim(), question: question.trim() }),
    })
    if (!res.ok) {
      const err = await res.text().catch(() => 'Unknown error')
      return NextResponse.json({ error: err || 'Ask failed' }, { status: res.status })
    }
    const data = await res.json()
    const bullets = [data.answer].filter(Boolean).flatMap((a: string) => a.split(/[.!?]+/).map((s: string) => s.trim()).filter(Boolean)).slice(0, 5)
    return NextResponse.json({
      answer: data.answer ?? '',
      bullets: data.bullets ?? bullets,
      riskReferences: data.riskReferences ?? [],
    })
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Copilot unavailable'
    return NextResponse.json({ error: msg }, { status: 502 })
  }
}
