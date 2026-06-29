import { Bar, BarChart, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import StatCard from '../components/StatCard'
import LiveFeed from '../components/LiveFeed'
import useWebSocket from '../hooks/useWebSocket'
import { useCost, useStats, useTokens } from '../hooks/useStats'

export default function Overview() {
  const { data: stats } = useStats()
  const { data: cost } = useCost()
  const { data: tokens } = useTokens()
  const { events } = useWebSocket()

  const statusData = [
    { name: 'Submitted', value: stats?.total_applied || 0, color: '#16a34a' },
    { name: 'Skipped', value: stats?.skipped || 0, color: '#ca8a04' },
    { name: 'Other', value: Math.max((stats?.total_jobs || 0) - (stats?.total_applied || 0) - (stats?.skipped || 0), 0), color: '#64748b' },
  ]

  const costOps = (cost?.breakdown || []).map((c) => ({ name: c.operation, cost: Number(c.cost || 0) }))
  const tokenOps = (tokens || []).map((t) => ({ name: t.operation, input: t.input_tokens, output: t.output_tokens }))

  return (
    <section className="space-y-4">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard title="Total Applied" value={stats?.total_applied ?? '-'} tone="green" />
        <StatCard title="Success Rate" value={`${stats?.success_rate ?? 0}%`} tone="teal" />
        <StatCard title="Skipped" value={stats?.skipped ?? 0} tone="amber" subtitle="No sponsorship" />
        <StatCard title="Manual Review" value={Math.max((stats?.total_jobs || 0) - (stats?.total_applied || 0) - (stats?.skipped || 0), 0)} tone="red" />
        <StatCard title="Total API Cost" value={`$${Number(stats?.cost_usd || 0).toFixed(4)}`} />
        <StatCard title="Replay Used" value={stats?.replay_used ?? 0} tone="green" subtitle="Zero-token submissions" />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <div className="card h-72 p-3 lg:col-span-2">
          <h3 className="mb-2 text-sm font-semibold text-slate-700">Token Usage by Operation</h3>
          <ResponsiveContainer width="100%" height="90%">
            <LineChart data={tokenOps}>
              <XAxis dataKey="name" fontSize={12} />
              <YAxis fontSize={12} />
              <Tooltip />
              <Line dataKey="input" stroke="#0f766e" strokeWidth={2} />
              <Line dataKey="output" stroke="#f59e0b" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card h-72 p-3">
          <h3 className="mb-2 text-sm font-semibold text-slate-700">Status Breakdown</h3>
          <ResponsiveContainer width="100%" height="90%">
            <PieChart>
              <Pie data={statusData} dataKey="value" nameKey="name" innerRadius={42} outerRadius={76}>
                {statusData.map((entry) => (
                  <Cell key={entry.name} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <div className="card h-72 p-3 lg:col-span-2">
          <h3 className="mb-2 text-sm font-semibold text-slate-700">Cost by Operation</h3>
          <ResponsiveContainer width="100%" height="90%">
            <BarChart data={costOps}>
              <XAxis dataKey="name" fontSize={12} />
              <YAxis fontSize={12} />
              <Tooltip />
              <Bar dataKey="cost" fill="#0f766e" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <LiveFeed events={events} />
      </div>
    </section>
  )
}
