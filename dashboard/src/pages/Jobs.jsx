import { useState } from 'react'
import JobRow from '../components/JobRow'
import { useJobs } from '../hooks/useStats'

export default function Jobs() {
  const { data: jobs = [], refetch } = useJobs()
  const [status, setStatus] = useState('all')

  const filtered = jobs.filter((j) => (status === 'all' ? true : j.status === status))

  async function retryJob(jobId) {
    await fetch(`/api/jobs/${jobId}/retry`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) })
    refetch()
  }

  return (
    <section className="space-y-3">
      <div className="card p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Jobs Table</h2>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded border border-slate-300 px-2 py-1 text-sm"
          >
            <option value="all">All</option>
            <option value="submitted">Submitted</option>
            <option value="failed">Failed</option>
            <option value="no_sponsorship">No Sponsorship</option>
            <option value="running">Running</option>
          </select>
        </div>

        <div className="mt-3 overflow-x-auto">
          <table className="min-w-full">
            <thead>
              <tr className="border-b border-slate-300 text-left text-xs uppercase text-slate-500">
                <th className="px-2 py-2">Company</th>
                <th className="px-2 py-2">Role</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Match</th>
                <th className="px-2 py-2">Replay</th>
                <th className="px-2 py-2">Cost</th>
                <th className="px-2 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((job) => (
                <JobRow key={job.id} job={job} onRetry={retryJob} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
