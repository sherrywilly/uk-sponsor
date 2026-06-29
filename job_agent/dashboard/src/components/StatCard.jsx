export default function StatCard({ title, value, tone = 'slate', sub }) {
  const toneClass = {
    green: 'bg-emerald-50 border-emerald-200 text-emerald-900',
    amber: 'bg-amber-50 border-amber-200 text-amber-900',
    red: 'bg-rose-50 border-rose-200 text-rose-900',
    blue: 'bg-sky-50 border-sky-200 text-sky-900',
    slate: 'bg-white border-slate-200 text-slate-900',
  }[tone]

  return (
    <article className={`rounded-2xl border p-4 shadow-sm ${toneClass}`}>
      <p className="text-xs font-semibold uppercase tracking-wide opacity-80">{title}</p>
      <p className="mt-2 text-3xl font-bold">{value}</p>
      {sub ? <p className="mt-2 text-sm opacity-80">{sub}</p> : null}
    </article>
  )
}
