import { Bar, BarChart, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import LiveFeed from '../components/LiveFeed'
import StatCard from '../components/StatCard'
import { useCost, useStats } from '../hooks/useStats'
import { useWebSocket } from '../hooks/useWebSocket'

export default function Overview() {
  const { data: stats } = useStats()
  const { data: cost } = useCost()
  const { events } = useWebSocket()

  const donut = [
    { name: 'submitted', value: stats?.submitted || 0 },
    { name: 'failed', value: stats?.failed || 0 },
    { name: 'skipped', value: stats?.skipped || 0 },
  ]

  return (
    <div className="space-y-6">
      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard title="Total Applied" value={stats?.submitted ?? 0} tone="success" />
        <StatCard title="Success Rate" value={`${stats?.success_rate ?? 0}%`} />
        <StatCard title="Skipped" value={stats?.skipped ?? 0} tone="warn" />
        <StatCard title="Manual Review" value={stats?.failed ?? 0} tone="danger" />
        <StatCard title="Total API Cost" value={`$${Number(stats?.total_cost_usd || 0).toFixed(4)}`} />
        <StatCard title="Replay Used" value={stats?.replay_used ?? 0} tone="success" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-xl bg-white p-4 shadow-sm lg:col-span-2">
          <h3 className="text-sm font-semibold">Applications per day</h3>
          <div className="mt-4 h-64">
            <ResponsiveContainer>
              <LineChart data={stats?.daily || []}>
                <XAxis dataKey="day" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="submitted" stroke="#1f8f5f" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-xl bg-white p-4 shadow-sm">
          <h3 className="text-sm font-semibold">Status breakdown</h3>
          <div className="mt-4 h-64">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={donut} dataKey="value" nameKey="name" outerRadius={90} fill="#1f8f5f" />
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-xl bg-white p-4 shadow-sm lg:col-span-2">
          <h3 className="text-sm font-semibold">Cost by operation</h3>
          <div className="mt-4 h-64">
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
        <LiveFeed events={events} />
      </div>
    </div>
  )
}
