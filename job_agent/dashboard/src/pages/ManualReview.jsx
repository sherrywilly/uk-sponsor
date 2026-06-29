import { useMemo } from 'react'
import { useJobs } from '../hooks/useStats'

export default function ManualReview() {
  const { data: jobs = [] } = useJobs()
  const items = useMemo(() => jobs.filter((j) => ['failed', 'captcha'].includes(j.status)), [jobs])

  return (
    <div className="rounded-xl bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold">Manual Review Queue</h3>
      <div className="mt-3 space-y-2">
        {items.length === 0 ? <p className="text-sm text-slate-500">No manual review items.</p> : null}
        {items.map((item) => (
          <div key={item.id} className="rounded-lg border border-slate-200 p-3">
            <p className="font-medium">{item.company || item.domain}</p>
            <p className="text-sm text-slate-500">Reason: {item.status}</p>
            <a className="text-sm text-blue-700" href={item.url} target="_blank" rel="noreferrer">Open in browser</a>
          </div>
        ))}
      </div>
    </div>
  )
}
