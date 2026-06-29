function badgeClass(status) {
  return `badge badge-${status || 'default'}`
}

export default function JobRow({ job, onRetry }) {
  return (
    <tr className="border-b border-slate-200 text-sm">
      <td className="px-2 py-2">{job.company || '-'}</td>
      <td className="px-2 py-2">{job.job_title || '-'}</td>
      <td className="px-2 py-2"><span className={badgeClass(job.status)}>{job.status || 'unknown'}</span></td>
      <td className="px-2 py-2">{job.match_score || '-'}</td>
      <td className="px-2 py-2">{job.replay_used ? 'Yes' : 'No'}</td>
      <td className="px-2 py-2">${Number(job.cost_usd || 0).toFixed(4)}</td>
      <td className="px-2 py-2">
        <button
          type="button"
          onClick={() => onRetry(job.id)}
          className="rounded border border-slate-300 px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
        >
          Retry
        </button>
      </td>
    </tr>
  )
}
