import { NextRequest, NextResponse } from 'next/server'
import { mapBackendToAnalysis, type DeedlyBackendResponse, type GraphPredictResponse } from '@/lib/map-backend'

const getBackendUrl = () =>
  process.env.BACKEND_URL || process.env.NEXT_PUBLIC_DEEDLY_API || 'http://localhost:8000'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params
  const base = getBackendUrl().replace(/\/$/, '')

  try {
    const analysisRes = await fetch(`${base}/api/analysis/${id}`)
    if (!analysisRes.ok) {
      const status = analysisRes.status
      const err = await analysisRes.text().catch(() => 'Not found')
      return NextResponse.json({ error: err || 'Report not found' }, { status })
    }

    const deedly = (await analysisRes.json()) as DeedlyBackendResponse & { analysisId?: string }
    deedly.analysisId = deedly.analysisId ?? id

    let graph: GraphPredictResponse | null = null
    try {
      await fetch(`${base}/api/graph/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ analysisId: id }),
      })
      const predictRes = await fetch(`${base}/api/graph/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ analysisId: id }),
      })
      if (predictRes.ok) {
        graph = (await predictRes.json()) as GraphPredictResponse
      }
    } catch {
      // Network risk optional
    }

    const analysis = mapBackendToAnalysis(deedly, graph)
    return NextResponse.json(analysis)
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Report unavailable'
    return NextResponse.json({ error: msg }, { status: 502 })
  }
}
