import { useEffect, useState } from "react";
import { Analytics, getJSON } from "../api";

export function OverviewPage() {
  const [analytics, setAnalytics] = useState<Analytics | null>(null);

  useEffect(() => {
    getJSON<Analytics>("/api/analytics").then(setAnalytics).catch(() => setAnalytics(null));
  }, []);

  return (
    <section className="panel">
      <h2>Overview</h2>
      <p>Real-time autonomous recruitment pipeline status.</p>
      {analytics ? (
        <div className="grid">
          <article className="metric">
            <span>Companies</span>
            <strong>{analytics.companies}</strong>
          </article>
          <article className="metric">
            <span>Jobs</span>
            <strong>{analytics.jobs}</strong>
          </article>
          <article className="metric">
            <span>Runs In Progress</span>
            <strong>{analytics.runs_in_progress}</strong>
          </article>
          <article className="metric">
            <span>Runs Completed</span>
            <strong>{analytics.runs_completed}</strong>
          </article>
        </div>
      ) : (
        <p>Loading analytics…</p>
      )}
    </section>
  );
}
