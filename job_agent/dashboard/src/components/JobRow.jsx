export default function JobRow({ job, onRetry }) {
  return (
    <tr className="border-b border-slate-100 hover:bg-slate-50">
      <td className="px-3 py-2">{job.company || '-'}</td>
      <td className="px-3 py-2">{job.job_title || '-'}</td>
      <td className="px-3 py-2">
        <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-semibold">{job.status}</span>
      </td>
      <td className="px-3 py-2">{job.match_score ?? '-'}</td>
      <td className="px-3 py-2">{job.applied_at ? new Date(job.applied_at).toLocaleString() : '-'}</td>
      <td className="px-3 py-2">{job.cv_path ? job.cv_path.split('/').pop() : '-'}</td>
      <td className="px-3 py-2">{job.replay_used ? 'Yes' : 'No'}</td>
      <td className="px-3 py-2">£{Number(job.cost_usd || 0).toFixed(4)}</td>
      <td className="px-3 py-2">
        <button
          type="button"
          onClick={() => onRetry(job.id)}
          className="rounded-md bg-slate-900 px-2 py-1 text-xs font-semibold text-white"
        >
          Retry
        </button>
      </td>
    </tr>
  )
}
