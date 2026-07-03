import { useEffect, useState } from "react";
import { getJSON, putJSON } from "../api";

export function SettingsPage() {
  const [concurrency, setConcurrency] = useState(2);
  const [message, setMessage] = useState("");

  useEffect(() => {
    getJSON<{ queue_concurrency: number }>("/api/settings")
      .then((s) => setConcurrency(s.queue_concurrency))
      .catch(() => null);
  }, []);

  async function save() {
    const data = await putJSON<{ queue_concurrency: number }>("/api/settings", {
      queue_concurrency: concurrency,
    });
    setMessage(`Saved desired concurrency ${data.queue_concurrency}. Restart backend to apply.`);
  }

  return (
    <section className="panel">
      <h2>Settings</h2>
      <label>
        Queue Concurrency
        <input
          type="number"
          min={1}
          max={10}
          value={concurrency}
          onChange={(e) => setConcurrency(Number(e.target.value))}
        />
      </label>
      <div>
        <button onClick={save}>Save Settings</button>
      </div>
      {message ? <p>{message}</p> : null}
    </section>
  );
}
