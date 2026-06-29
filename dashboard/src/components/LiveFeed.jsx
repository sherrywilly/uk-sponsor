function badgeClass(status) {
  if (!status) return 'badge badge-default'
  return `badge badge-${status}`
}

export default function LiveFeed({ events = [] }) {
  return (
    <div className="card p-4">
      <h3 className="text-lg font-semibold">Live Feed</h3>
      <div className="mt-3 space-y-2">
        {events.length === 0 ? <p className="text-sm text-slate-500">Waiting for WebSocket events...</p> : null}
        {events.slice(0, 10).map((event, idx) => (
          <div key={`${event.event}-${idx}`} className="rounded-md border border-slate-200 px-3 py-2 text-sm">
            <div className="flex items-center justify-between gap-3">
              <span className="font-semibold text-slate-700">{event.event || 'event'}</span>
              <span className={badgeClass(event.status || '')}>{event.status || 'info'}</span>
            </div>
            <p className="mt-1 break-all text-xs text-slate-500">{event.url || event.message || JSON.stringify(event)}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
