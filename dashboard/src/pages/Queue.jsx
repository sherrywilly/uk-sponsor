import { useState } from 'react'
import { useStats } from '../hooks/useStats'

export default function Queue() {
  const { data: stats, refetch } = useStats()
  const [urls, setUrls] = useState('')

  async function addToQueue() {
    const list = urls.split('\n').map((u) => u.trim()).filter(Boolean)
    if (!list.length) return
    await fetch('/api/jobs/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urls: list }),
    })
    setUrls('')
    refetch()
  }

  async function start() {
    await fetch('/api/agent/start', { method: 'POST' })
    refetch()
  }

  async function pause() {
    await fetch('/api/agent/pause', { method: 'POST' })
    refetch()
  }

  return (
    <section className="space-y-3">
      <div className="card p-4">
        <h2 className="text-lg font-semibold">Queue Manager</h2>
        <p className="mt-1 text-sm text-slate-500">Paste one job URL per line, then start processing.</p>
        <textarea
          value={urls}
          onChange={(e) => setUrls(e.target.value)}
          rows={8}
          className="mt-3 w-full rounded-md border border-slate-300 p-2 text-sm"
          placeholder="https://jobs.lever.co/company/role"
        />
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" onClick={addToQueue} className="rounded-md bg-teal-700 px-3 py-2 text-sm font-semibold text-white">Add URLs</button>
          <button type="button" onClick={start} className="rounded-md border border-teal-700 px-3 py-2 text-sm font-semibold text-teal-700">Start</button>
          <button type="button" onClick={pause} className="rounded-md border border-amber-600 px-3 py-2 text-sm font-semibold text-amber-700">Pause</button>
        </div>
      </div>

      <div className="card p-4">
        <h3 className="font-semibold">Queue Status</h3>
        <p className="mt-1 text-sm text-slate-600">Running: {stats?.agent?.running ? 'Yes' : 'No'} | Paused: {stats?.agent?.paused ? 'Yes' : 'No'} | Pending: {stats?.agent?.queued ?? 0}</p>
      </div>
    </section>
  )
}
