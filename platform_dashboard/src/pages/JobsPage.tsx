import { useEffect, useState } from "react";
import { getJSON } from "../api";

type Job = {
  id: number;
  title: string;
  location: string | null;
  employment_type: string | null;
  ats_provider: string | null;
  created_at: string;
};

export function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);

  useEffect(() => {
    getJSON<Job[]>("/api/jobs").then(setJobs).catch(() => setJobs([]));
  }, []);

  return (
    <section className="panel">
      <h2>Jobs</h2>
      <table>
        <thead>
          <tr>
            <th>Title</th>
            <th>Location</th>
            <th>Type</th>
            <th>ATS</th>
            <th>Discovered</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id}>
              <td>{job.title}</td>
              <td>{job.location ?? "-"}</td>
              <td>{job.employment_type ?? "-"}</td>
              <td>{job.ats_provider ?? "unknown"}</td>
              <td>{new Date(job.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
