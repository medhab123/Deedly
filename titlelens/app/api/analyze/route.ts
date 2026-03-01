import { NextRequest, NextResponse } from 'next/server'
import type { BuyerPersona } from '@/lib/types'
import { mapBackendToAnalysis, type DeedlyBackendResponse, type GraphPredictResponse } from '@/lib/map-backend'

const getBackendUrl = () =>
  process.env.BACKEND_URL || process.env.NEXT_PUBLIC_DEEDLY_API || 'http://localhost:8000'

export async function POST(request: NextRequest) {
  const body = await request.json()
  const { address, persona } = body as { address: string; persona: BuyerPersona }

  if (!address?.trim()) {
    return NextResponse.json({ error: 'Address required' }, { status: 400 })
  }

  const base = getBackendUrl().replace(/\/$/, '')

  try {
    const analyzeRes = await fetch(`${base}/api/deedly/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address: address.trim(), persona: persona || 'Family' }),
    })
    if (!analyzeRes.ok) {
      const err = await analyzeRes.text().catch(() => 'Unknown error')
      return NextResponse.json({ error: err || 'Analysis failed' }, { status: analyzeRes.status })
    }

    const deedly: DeedlyBackendResponse & { analysisId?: string } = await analyzeRes.json()
    const analysisId = deedly.analysisId

    let graph: GraphPredictResponse | null = null
    if (analysisId) {
      try {
        await fetch(`${base}/api/graph/ingest`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ analysisId }),
        })
        const predictRes = await fetch(`${base}/api/graph/predict`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ analysisId }),
        })
        if (predictRes.ok) {
          graph = (await predictRes.json()) as GraphPredictResponse
        }
      } catch {
        // Network risk optional
      }
    }

    const analysis = mapBackendToAnalysis(deedly, graph)
    return NextResponse.json(analysis)
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Analysis unavailable'
    return NextResponse.json({ error: msg }, { status: 502 })
  }
}
