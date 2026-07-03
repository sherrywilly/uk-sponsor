import { Link, useLocation } from "react-router-dom";

const navItems = [
  ["/", "Overview"],
  ["/companies", "Companies"],
  ["/jobs", "Jobs"],
  ["/live-browser", "Live Browser"],
  ["/activity", "Agent Activity"],
  ["/history", "Action History"],
  ["/analytics", "Analytics"],
  ["/csv", "CSV Export"],
  ["/settings", "Settings"],
] as const;

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  return (
    <div className="shell">
      <aside className="sidebar">
        <h1>RecruitOps AI</h1>
        <p>Autonomous hiring crawler</p>
        <nav>
          {navItems.map(([path, label]) => (
            <Link key={path} className={location.pathname === path ? "active" : ""} to={path}>
              {label}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}
