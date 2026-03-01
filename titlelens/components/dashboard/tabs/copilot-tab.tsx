'use client'

import { useState, useRef, useEffect } from 'react'
import { useCopilot } from '@/lib/store'
import { Send, Loader2 } from 'lucide-react'

const SUGGESTED_QUESTIONS = [
  'Is this a safe long-term investment?',
  'What are the top 3 risks?',
  'Should I request a title search?',
  'How does the network risk affect me?',
]

export function CopilotTab({ analysisId }: { analysisId: string }) {
  const { messages, sendMessage } = useCopilot()
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async (question?: string) => {
    const q = question || input.trim()
    if (!q || isSending) return
    setInput('')
    setIsSending(true)
    await sendMessage(analysisId, q)
    setIsSending(false)
  }

  return (
    <div className="flex flex-col gap-4 animate-fade-lift-in">
      {/* Chat container */}
      <div className="glass-card flex flex-col rounded-xl overflow-hidden" style={{ minHeight: '480px' }}>
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-6">
              <p className="font-sans text-sm text-muted-foreground text-center max-w-sm">
                Ask anything about this property analysis. Get insights, risk explanations, and actionable next steps.
              </p>
              {/* Suggested questions */}
              <div className="flex flex-wrap justify-center gap-2">
                {SUGGESTED_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => handleSend(q)}
                    className="rounded-full border border-border bg-secondary/20 px-3 py-1.5 font-mono text-xs text-muted-foreground transition-colors hover:border-teal/30 hover:text-cream"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[85%] rounded-xl px-4 py-3 ${
                      msg.role === 'user'
                        ? 'bg-teal/15 border border-teal/20 text-cream'
                        : 'bg-secondary/40 border border-border text-cream/90'
                    }`}
                  >
                    <p className="font-sans text-sm leading-relaxed whitespace-pre-wrap">
                      {msg.content}
                    </p>
                  </div>
                </div>
              ))}
              {isSending && (
                <div className="flex justify-start">
                  <div className="rounded-xl bg-secondary/40 border border-border px-4 py-3">
                    <Loader2 className="size-4 text-teal animate-spin" />
                  </div>
                </div>
              )}
              <div ref={endRef} />
            </div>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-border p-4">
          <div className="flex items-center gap-3">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder="Ask anything — 'Is this a safe long-term investment?'"
              className="flex-1 bg-transparent font-sans text-sm text-cream placeholder:text-muted-foreground focus:outline-none"
              disabled={isSending}
            />
            <button
              onClick={() => handleSend()}
              disabled={!input.trim() || isSending}
              className="shrink-0 rounded-lg bg-teal/15 p-2 text-teal transition-colors hover:bg-teal/25 disabled:opacity-30 disabled:cursor-not-allowed"
              aria-label="Send message"
            >
              <Send className="size-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
