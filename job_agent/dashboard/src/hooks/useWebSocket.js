import { useEffect, useMemo, useState } from 'react'

const WS_BASE = (import.meta.env.VITE_WS_BASE || 'ws://localhost:8000').replace(/\/$/, '')

export function useWebSocket() {
  const [events, setEvents] = useState([])

  useEffect(() => {
    const ws = new WebSocket(`${WS_BASE}/ws/live`)

    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data)
        setEvents((prev) => [parsed, ...prev].slice(0, 10))
      } catch {
        // ignore malformed events
      }
    }

    return () => ws.close()
  }, [])

  return useMemo(() => ({ events }), [events])
}
