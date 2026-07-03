import { LiveFeed } from "../components/LiveFeed";

export function HistoryPage() {
  return (
    <section className="panel">
      <h2>Action History</h2>
      <p>Historical and live action stream from all worker runs.</p>
      <LiveFeed />
    </section>
  );
}
