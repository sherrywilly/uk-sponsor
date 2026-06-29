import { Bar, BarChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useCost, useStats, useTokens } from '../hooks/useStats'
import StatCard from '../components/StatCard'

export default function TokenAnalytics() {
  const { data: tokens } = useTokens()
  const { data: stats } = useStats()
  const { data: cost } = useCost()

  const lineData = [
    { name: 'input', value: tokens?.input || 0 },
    { name: 'output', value: tokens?.output || 0 },
    { name: 'cached', value: tokens?.cached || 0 },
  ]

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <StatCard title="Total spent" value={`$${Number(cost?.total_usd || 0).toFixed(4)}`} />
        <StatCard title="Saved by cache" value={`$${Number(cost?.saved_by_cache || 0).toFixed(4)}`} tone="success" />
        <StatCard title="Saved by replay" value={`$${Number(cost?.saved_by_replay || 0).toFixed(4)}`} tone="success" />
        <StatCard title="Avg cost/app" value={`$${((cost?.total_usd || 0) / Math.max(stats?.total || 1, 1)).toFixed(4)}`} />
        <StatCard title="Projected" value={`$${(((cost?.total_usd || 0) / Math.max(stats?.total || 1, 1)) * 100).toFixed(2)}`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl bg-white p-4 shadow-sm">
          <h3 className="text-sm font-semibold">Token Usage</h3>
          <div className="mt-4 h-60">
            <ResponsiveContainer>
              <LineChart data={lineData}>
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Line dataKey="value" stroke="#1f8f5f" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-xl bg-white p-4 shadow-sm">
          <h3 className="text-sm font-semibold">Cost by operation</h3>
          <div className="mt-4 h-60">
            <ResponsiveContainer>
              <BarChart data={cost?.by_operation || []}>
                <XAxis dataKey="operation" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="cost" fill="#2f6ca8" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  )
}
