import { useEffect, useState } from "react";
import { getJSON } from "../api";

type Action = {
  id: number;
  action_type: string;
  details: string;
  created_at: string;
};

export function ActivityPage() {
  const [actions, setActions] = useState<Action[]>([]);

  useEffect(() => {
    getJSON<Action[]>("/api/activity").then(setActions).catch(() => setActions([]));
  }, []);

  return (
    <section className="panel">
      <h2>Agent Activity</h2>
      <table>
        <thead>
          <tr>
            <th>Action</th>
            <th>Details</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody>
          {actions.map((action) => (
            <tr key={action.id}>
              <td>{action.action_type}</td>
              <td>{action.details}</td>
              <td>{new Date(action.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
