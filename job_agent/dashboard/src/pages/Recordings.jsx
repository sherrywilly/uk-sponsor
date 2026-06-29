import { useMemo, useState } from 'react'
import RecordingViewer from '../components/RecordingViewer'
import { useRecordings } from '../hooks/useStats'

export default function Recordings() {
  const { data: recordings = [] } = useRecordings()
  const [selectedId, setSelectedId] = useState(null)

  const selected = useMemo(() => recordings.find((r) => r.id === selectedId), [recordings, selectedId])

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="overflow-auto rounded-xl bg-white p-4 shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-slate-500">
              <th className="py-2">Domain</th>
              <th className="py-2">ATS</th>
              <th className="py-2">Success</th>
              <th className="py-2">Fail</th>
            </tr>
          </thead>
          <tbody>
            {recordings.map((row) => (
              <tr key={row.id} className="cursor-pointer border-b border-slate-100" onClick={() => setSelectedId(row.id)}>
                <td className="py-3">{row.domain || '-'}</td>
                <td className="py-3">{row.ats_type}</td>
                <td className="py-3">{row.success_count}</td>
                <td className="py-3">{row.fail_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <RecordingViewer recording={selected} />
    </div>
  )
}
