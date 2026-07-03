import { FormEvent, useEffect, useState } from "react";
import { getJSON, postJSON } from "../api";

type Company = {
  id: number;
  name: string;
  domain: string;
  homepage_url: string;
  careers_url: string | null;
  ats_provider: string | null;
};

export function CompaniesPage() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");

  const refresh = () => getJSON<Company[]>("/api/companies").then(setCompanies).catch(() => setCompanies([]));

  useEffect(() => {
    refresh();
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!name || !url) {
      return;
    }
    await postJSON("/api/companies", { name, homepage_url: url });
    setName("");
    setUrl("");
    refresh();
  }

  return (
    <section className="panel">
      <h2>Companies</h2>
      <form onSubmit={onSubmit} className="grid">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Company name" />
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://company.com" />
        <button type="submit">Queue Crawl</button>
      </form>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Domain</th>
            <th>Careers URL</th>
            <th>ATS</th>
          </tr>
        </thead>
        <tbody>
          {companies.map((company) => (
            <tr key={company.id}>
              <td>{company.name}</td>
              <td>{company.domain}</td>
              <td>{company.careers_url ?? "-"}</td>
              <td>{company.ats_provider ?? "unknown"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
