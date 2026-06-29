import { useWebSocket } from '../hooks/useWebSocket'

export default function LiveFeed() {
  const events = useWebSocket(10)

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-lg font-bold">Live Feed</h3>
      <ul className="space-y-2 text-sm">
        {events.length === 0 ? <li className="text-slate-500">No events yet.</li> : null}
        {events.map((item, idx) => (
          <li key={idx} className="rounded-lg border border-slate-100 bg-slate-50 p-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold">{item.event}</span>
              <span className="text-xs text-slate-500">{new Date(item.timestamp).toLocaleTimeString()}</span>
            </div>
            <pre className="mt-1 overflow-x-auto text-xs text-slate-700">
              {JSON.stringify(item.payload, null, 2)}
            </pre>
          </li>
        ))}
      </ul>
    </section>
  )
}
