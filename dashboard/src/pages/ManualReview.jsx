import { useJobs } from '../hooks/useStats'

const needsManual = new Set(['captcha', 'failed'])

export default function ManualReview() {
  const { data: jobs = [] } = useJobs()
  const rows = jobs.filter((j) => needsManual.has(j.status))

  async function retry(jobId) {
    await fetch(`/api/jobs/${jobId}/retry`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
  }

  return (
    <section className="card p-4">
      <h2 className="text-lg font-semibold">Manual Review</h2>
      <p className="mt-1 text-sm text-slate-500">Jobs requiring human intervention.</p>

      <div className="mt-3 space-y-2">
        {rows.length === 0 ? <p className="text-sm text-slate-500">No manual review items.</p> : null}
        {rows.map((j) => (
          <div key={j.id} className="rounded border border-slate-200 p-3 text-sm">
            <p className="font-semibold text-slate-800">{j.company || j.url}</p>
            <p className="text-slate-500">Reason: {j.status}</p>
            <div className="mt-2 flex gap-2">
              <a href={j.url} target="_blank" rel="noreferrer" className="rounded border border-slate-300 px-2 py-1 text-xs font-semibold text-slate-700">Open URL</a>
              <button type="button" onClick={() => retry(j.id)} className="rounded border border-teal-700 px-2 py-1 text-xs font-semibold text-teal-700">Retry</button>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
