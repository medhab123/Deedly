import useSWR from 'swr'
import type { AnalysisResult, BuyerPersona, CopilotMessage } from './types'

// SWR-based store for sharing analysis state across components
const ANALYSIS_KEY = 'deedly-analysis'

const fetcher = async ([url, body]: [string, object]) => {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error('Analysis unavailable')
  return res.json()
}

export function useAnalysis() {
  const { data, error, isLoading, mutate } = useSWR<AnalysisResult>(
    ANALYSIS_KEY,
    null,
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
    }
  )

  const analyze = async (address: string, persona: BuyerPersona) => {
    const result = await fetcher(['/api/analyze', { address, persona }])
    mutate(result, false)
    return result
  }

  const clear = () => {
    mutate(undefined, false)
  }

  return { analysis: data, error, isLoading, analyze, clear, mutate }
}

export function useCopilot() {
  const { data: messages, mutate } = useSWR<CopilotMessage[]>(
    'deedly-copilot-messages',
    null,
    {
      fallbackData: [],
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
    }
  )

  const sendMessage = async (analysisId: string, question: string) => {
    const userMsg: CopilotMessage = { role: 'user', content: question }
    const currentMessages = messages || []
    mutate([...currentMessages, userMsg], false)

    try {
      const res = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ analysisId, question }),
      })
      const data = await res.json()
      const assistantMsg: CopilotMessage = { role: 'assistant', content: data.answer }
      mutate([...currentMessages, userMsg, assistantMsg], false)
    } catch {
      const errorMsg: CopilotMessage = { role: 'assistant', content: 'I wasn\'t able to process that request. Please try again.' }
      mutate([...currentMessages, userMsg, errorMsg], false)
    }
  }

  const clearMessages = () => mutate([], false)

  return { messages: messages || [], sendMessage, clearMessages }
}
