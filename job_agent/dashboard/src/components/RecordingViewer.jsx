export default function RecordingViewer({ recording }) {
  if (!recording) return null

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-950 p-3 text-xs text-emerald-200">
      <pre className="overflow-x-auto">{recording.script_json}</pre>
    </div>
  )
}
