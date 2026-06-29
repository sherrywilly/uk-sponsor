export default function StatCard({ title, value, subtitle = '', tone = 'slate' }) {
  const toneClass = {
    green: 'text-green-700',
    amber: 'text-amber-700',
    red: 'text-red-700',
    teal: 'text-teal-700',
    slate: 'text-slate-800',
  }[tone] || 'text-slate-800'

  return (
    <div className="card p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      <p className={`mt-2 text-2xl font-bold ${toneClass}`}>{value}</p>
      {subtitle ? <p className="mt-1 text-xs text-slate-500">{subtitle}</p> : null}
    </div>
  )
}
