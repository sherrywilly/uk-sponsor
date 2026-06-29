export default function RecordingViewer({ recording }) {
  if (!recording) {
    return (
      <div className="card p-4 text-sm text-slate-500">
        Select a recording row to inspect full JSON script.
      </div>
    )
  }

  return (
    <div className="card p-4">
      <h3 className="text-lg font-semibold">{recording.domain} script</h3>
      <pre className="mt-3 max-h-[420px] overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-100">
        {JSON.stringify(JSON.parse(recording.script_json || '{}'), null, 2)}
      </pre>
    </div>
  )
}
