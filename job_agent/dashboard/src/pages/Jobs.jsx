import { useState } from 'react'
import JobRow from '../components/JobRow'
import { useJobs } from '../hooks/useStats'

export default function Jobs() {
  const [status, setStatus] = useState('')
  const { data: jobs = [] } = useJobs({ status })

  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-white p-4 shadow-sm">
        <label className="text-sm font-medium">Filter by status</label>
        <select className="ml-3 rounded-md border border-slate-300 p-2" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All</option>
          <option value="submitted">Submitted</option>
          <option value="failed">Failed</option>
          <option value="skipped_no_sponsorship">Skipped</option>
        </select>
      </div>

      <div className="overflow-auto rounded-xl bg-white p-4 shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-slate-500">
              <th className="px-2 py-2">Company</th>
              <th className="px-2 py-2">Role</th>
              <th className="px-2 py-2">Status</th>
              <th className="px-2 py-2">Match</th>
              <th className="px-2 py-2">Mode</th>
              <th className="px-2 py-2">Cost</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <JobRow key={job.id} job={job} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
