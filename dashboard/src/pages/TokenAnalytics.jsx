import { Bar, BarChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import StatCard from '../components/StatCard'
import { useCost, useTokens } from '../hooks/useStats'

export default function TokenAnalytics() {
  const { data: tokens = [] } = useTokens()
  const { data: cost } = useCost()

  const lineData = tokens.map((t) => ({
    op: t.operation,
    in: Number(t.input_tokens || 0),
    out: Number(t.output_tokens || 0),
    cached: Number(t.cached_tokens || 0),
  }))
  const barData = (cost?.breakdown || []).map((c) => ({ op: c.operation, cost: Number(c.cost || 0) }))

  return (
    <section className="space-y-3">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
        <StatCard title="Total Spent" value={`$${Number(cost?.total_cost || 0).toFixed(4)}`} />
        <StatCard title="Saved by Cache" value={`$${Number(cost?.saved_by_cache || 0).toFixed(4)}`} tone="green" />
        <StatCard title="Saved by Replay" value={`$${Number(cost?.saved_by_replay || 0).toFixed(4)}`} tone="green" />
        <StatCard title="Avg Cost / App" value={`$${((cost?.total_cost || 0) / Math.max(tokens.length, 1)).toFixed(4)}`} tone="teal" />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="card h-72 p-3">
          <h3 className="mb-2 text-sm font-semibold text-slate-700">Daily Token Usage (by operation)</h3>
          <ResponsiveContainer width="100%" height="90%">
            <LineChart data={lineData}>
              <XAxis dataKey="op" fontSize={12} />
              <YAxis fontSize={12} />
              <Tooltip />
              <Line dataKey="in" stroke="#0f766e" />
              <Line dataKey="out" stroke="#f59e0b" />
              <Line dataKey="cached" stroke="#9333ea" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card h-72 p-3">
          <h3 className="mb-2 text-sm font-semibold text-slate-700">Cost by Operation</h3>
          <ResponsiveContainer width="100%" height="90%">
            <BarChart data={barData}>
              <XAxis dataKey="op" fontSize={12} />
              <YAxis fontSize={12} />
              <Tooltip />
              <Bar dataKey="cost" fill="#0f766e" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  )
}
