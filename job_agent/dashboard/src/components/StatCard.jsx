export default function StatCard({ title, value, tone = 'default', subtitle }) {
  const toneMap = {
    default: 'border-slate-200',
    success: 'border-emerald-300',
    warn: 'border-amber-300',
    danger: 'border-rose-300',
  }

  return (
    <div className={`rounded-xl border-2 ${toneMap[tone]} bg-white p-4 shadow-sm`}>
      <p className="text-xs uppercase tracking-wider text-slate-500">{title}</p>
      <p className="mt-2 text-3xl font-semibold text-slate-900">{value}</p>
      {subtitle ? <p className="mt-1 text-sm text-slate-500">{subtitle}</p> : null}
    </div>
  )
}
