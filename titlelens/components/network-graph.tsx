'use client'

import { useEffect, useRef } from 'react'

interface Node {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  opacity: number
  phase: number
}

interface Edge {
  from: number
  to: number
  opacity: number
}

export function NetworkGraph({ className }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animationRef = useRef<number>(0)
  const nodesRef = useRef<Node[]>([])
  const edgesRef = useRef<Edge[]>([])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const resize = () => {
      canvas.width = canvas.offsetWidth * window.devicePixelRatio
      canvas.height = canvas.offsetHeight * window.devicePixelRatio
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio)
    }
    resize()
    window.addEventListener('resize', resize)

    // Initialize nodes
    const nodeCount = 40
    const w = canvas.offsetWidth
    const h = canvas.offsetHeight
    
    nodesRef.current = Array.from({ length: nodeCount }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      radius: Math.random() * 2 + 1,
      opacity: Math.random() * 0.4 + 0.1,
      phase: Math.random() * Math.PI * 2,
    }))

    // Create edges between nearby nodes
    const updateEdges = () => {
      const newEdges: Edge[] = []
      const nodes = nodesRef.current
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x
          const dy = nodes[i].y - nodes[j].y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < 150) {
            newEdges.push({
              from: i,
              to: j,
              opacity: (1 - dist / 150) * 0.15,
            })
          }
        }
      }
      edgesRef.current = newEdges
    }

    let time = 0
    const animate = () => {
      time += 0.01
      const cw = canvas.offsetWidth
      const ch = canvas.offsetHeight
      ctx.clearRect(0, 0, cw, ch)

      // Update nodes
      const nodes = nodesRef.current
      for (const node of nodes) {
        node.x += node.vx
        node.y += node.vy

        if (node.x < 0 || node.x > cw) node.vx *= -1
        if (node.y < 0 || node.y > ch) node.vy *= -1

        node.opacity = 0.15 + Math.sin(time + node.phase) * 0.1
      }

      updateEdges()

      // Draw edges
      for (const edge of edgesRef.current) {
        const from = nodes[edge.from]
        const to = nodes[edge.to]
        ctx.beginPath()
        ctx.moveTo(from.x, from.y)
        ctx.lineTo(to.x, to.y)
        ctx.strokeStyle = `rgba(120, 93, 50, ${edge.opacity})`
        ctx.lineWidth = 0.5
        ctx.stroke()
      }

      // Draw nodes
      for (const node of nodes) {
        ctx.beginPath()
        ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(120, 93, 50, ${node.opacity})`
        ctx.fill()
      }

      animationRef.current = requestAnimationFrame(animate)
    }

    animate()

    return () => {
      cancelAnimationFrame(animationRef.current)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{ width: '100%', height: '100%' }}
    />
  )
}
