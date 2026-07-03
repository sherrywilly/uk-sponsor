import { useEffect, useState } from "react";
import { Analytics, getJSON } from "../api";

export function AnalyticsPage() {
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [queue, setQueue] = useState<{ queue_size: number; concurrency: number } | null>(null);

  useEffect(() => {
    getJSON<Analytics>("/api/analytics").then(setAnalytics).catch(() => setAnalytics(null));
    getJSON<{ queue_size: number; concurrency: number }>("/api/queue/status")
      .then(setQueue)
      .catch(() => setQueue(null));
  }, []);

  return (
    <section className="panel">
      <h2>Analytics</h2>
      <div className="grid">
        <article className="metric">
          <span>Total Companies</span>
          <strong>{analytics?.companies ?? "-"}</strong>
        </article>
        <article className="metric">
          <span>Total Jobs</span>
          <strong>{analytics?.jobs ?? "-"}</strong>
        </article>
        <article className="metric">
          <span>Queue Size</span>
          <strong>{queue?.queue_size ?? "-"}</strong>
        </article>
        <article className="metric">
          <span>Concurrency</span>
          <strong>{queue?.concurrency ?? "-"}</strong>
        </article>
      </div>
    </section>
  );
}
