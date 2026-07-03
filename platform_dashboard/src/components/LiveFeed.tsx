import { useEffect, useMemo, useState } from "react";

type FeedEvent = {
  action_type: string;
  details: string;
  timestamp: string;
};

export function LiveFeed() {
  const [events, setEvents] = useState<FeedEvent[]>([]);

  useEffect(() => {
    const ws = new WebSocket(`${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/events`);
    ws.onopen = () => ws.send("subscribe");
    ws.onmessage = (message) => {
      const parsed = JSON.parse(message.data) as FeedEvent;
      setEvents((prev) => [parsed, ...prev].slice(0, 80));
    };
    return () => ws.close();
  }, []);

  const highlighted = useMemo(
    () =>
      events.map((event, i) => (
        <li key={`${event.timestamp}-${i}`}>
          <strong>{event.action_type}</strong>
          <span>{event.details}</span>
          <time>{new Date(event.timestamp).toLocaleTimeString()}</time>
        </li>
      )),
    [events]
  );

  return <ul className="feed-list">{highlighted}</ul>;
}
