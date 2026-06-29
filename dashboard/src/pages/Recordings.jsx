import { useState } from 'react'
import RecordingViewer from '../components/RecordingViewer'
import { useRecordings } from '../hooks/useStats'

export default function Recordings() {
  const { data: recordings = [] } = useRecordings()
  const [selected, setSelected] = useState(null)

  return (
    <section className="grid grid-cols-1 gap-3 lg:grid-cols-3">
      <div className="card p-4 lg:col-span-2">
        <h2 className="text-lg font-semibold">Recordings Library</h2>
        <p className="mt-1 text-sm text-slate-500">Domain and ATS scripts used for zero-token replay.</p>

        <div className="mt-3 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-slate-300 text-left text-xs uppercase text-slate-500">
                <th className="px-2 py-2">Domain</th>
                <th className="px-2 py-2">ATS</th>
                <th className="px-2 py-2">Success</th>
                <th className="px-2 py-2">Fail</th>
                <th className="px-2 py-2">Last Used</th>
              </tr>
            </thead>
            <tbody>
              {recordings.map((r) => (
                <tr
                  key={r.id}
                  className="cursor-pointer border-b border-slate-200 hover:bg-slate-50"
                  onClick={() => setSelected(r)}
                >
                  <td className="px-2 py-2">{r.domain}</td>
                  <td className="px-2 py-2">{r.ats_type}</td>
                  <td className="px-2 py-2">{r.success_count}</td>
                  <td className="px-2 py-2">{r.fail_count}</td>
                  <td className="px-2 py-2">{r.last_used || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <RecordingViewer recording={selected} />
    </section>
  )
}
