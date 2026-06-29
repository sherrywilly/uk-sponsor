export default function LiveFeed({ events }) {
  return (
    <div className="rounded-xl bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-900">Live Feed</h3>
      <div className="mt-3 space-y-2">
        {events.length === 0 ? <p className="text-sm text-slate-500">No events yet</p> : null}
        {events.map((event, index) => (
          <div key={`${event.event}-${index}`} className="rounded-lg border border-slate-200 p-2 text-sm">
            <span className="font-medium text-slate-800">{event.event}</span>
            <p className="text-slate-500">{JSON.stringify(event.payload)}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
