export default function JobRow({ job }) {
  return (
    <tr className="border-b border-slate-100">
      <td className="px-2 py-3">{job.company || '-'}</td>
      <td className="px-2 py-3">{job.job_title || '-'}</td>
      <td className="px-2 py-3">{job.status}</td>
      <td className="px-2 py-3">{job.match_score ?? '-'}</td>
      <td className="px-2 py-3">{job.replay_used ? 'Replay' : 'Claude'}</td>
      <td className="px-2 py-3">${Number(job.cost_usd || 0).toFixed(4)}</td>
    </tr>
  )
}
