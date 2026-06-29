import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/api'

export function useWebSocket(limit = 10) {
  const [events, setEvents] = useState([])

  useEffect(() => {
    const wsUrl = API_BASE.replace('http', 'ws') + '/ws/live'
    const ws = new WebSocket(wsUrl)

    ws.onmessage = (event) => {
      const parsed = JSON.parse(event.data)
      setEvents((prev) => [parsed, ...prev].slice(0, limit))
    }

    const keepAlive = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send('ping')
    }, 10000)

    return () => {
      clearInterval(keepAlive)
      ws.close()
    }
  }, [limit])

  return events
}
