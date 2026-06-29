import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiPost } from '../lib/api'

export default function Queue() {
  const [rawUrls, setRawUrls] = useState('')
  const queryClient = useQueryClient()

  const addJobs = useMutation({
    mutationFn: (urls) => apiPost('/api/jobs/add', { urls }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['jobs'] }),
  })

  const startAgent = useMutation({
    mutationFn: () => apiPost('/api/agent/start'),
  })

  const pauseAgent = useMutation({
    mutationFn: () => apiPost('/api/agent/pause'),
  })

  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-white p-4 shadow-sm">
        <h3 className="text-sm font-semibold">Add URLs</h3>
        <textarea
          className="mt-3 h-40 w-full rounded-md border border-slate-300 p-2 text-sm"
          value={rawUrls}
          onChange={(e) => setRawUrls(e.target.value)}
          placeholder="Paste one URL per line"
        />
        <button
          className="mt-3 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white"
          onClick={() => {
            const urls = rawUrls.split('\n').map((u) => u.trim()).filter(Boolean)
            addJobs.mutate(urls)
          }}
        >
          Queue Jobs
        </button>
      </div>

      <div className="rounded-xl bg-white p-4 shadow-sm">
        <h3 className="text-sm font-semibold">Controls</h3>
        <div className="mt-3 flex gap-2">
          <button className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white" onClick={() => startAgent.mutate()}>
            Start
          </button>
          <button className="rounded-md bg-amber-600 px-4 py-2 text-sm font-medium text-white" onClick={() => pauseAgent.mutate()}>
            Pause
          </button>
        </div>
      </div>
    </div>
  )
}
