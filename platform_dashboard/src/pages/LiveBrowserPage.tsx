import { LiveFeed } from "../components/LiveFeed";

export function LiveBrowserPage() {
  return (
    <section className="panel">
      <h2>Live Browser</h2>
      <p>Streaming browser actions in real-time.</p>
      <LiveFeed />
    </section>
  );
}
