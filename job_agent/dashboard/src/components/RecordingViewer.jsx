export default function RecordingViewer({ recording }) {
  if (!recording) {
    return <p className="text-sm text-slate-500">Select a recording row to inspect script JSON.</p>
  }

  return (
    <pre className="max-h-[26rem] overflow-auto rounded-xl bg-slate-900 p-4 text-xs text-slate-100">
      {recording.script_json}
    </pre>
  )
}
