import { useState } from "react";
import { postJSON } from "../api";

export function CsvExportPage() {
  const [result, setResult] = useState<string>("");

  async function doExport() {
    const data = await postJSON<{ path: string; count: number }>("/api/export/csv", {});
    setResult(`Exported ${data.count} jobs to ${data.path}`);
  }

  return (
    <section className="panel">
      <h2>CSV Export</h2>
      <p>Generate a full jobs export from the deduplicated database.</p>
      <button onClick={doExport}>Export CSV</button>
      {result ? <p>{result}</p> : null}
    </section>
  );
}
