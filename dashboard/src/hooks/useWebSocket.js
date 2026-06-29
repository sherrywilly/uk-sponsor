import { useEffect, useRef, useState } from 'react'

export default function useWebSocket(url = '/ws/live') {
  const [events, setEvents] = useState([])
  const wsRef = useRef(null)

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const socket = new WebSocket(`${protocol}://${window.location.host}${url}`)
    wsRef.current = socket

    socket.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data)
        setEvents((prev) => [parsed, ...prev].slice(0, 20))
      } catch {
        setEvents((prev) => [{ event: 'message', raw: event.data }, ...prev].slice(0, 20))
      }
    }

    socket.onopen = () => socket.send('ping')
    return () => socket.close()
  }, [url])

  return { events }
}
