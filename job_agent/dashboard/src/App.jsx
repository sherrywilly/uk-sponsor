import { NavLink, Route, Routes } from 'react-router-dom'
import Jobs from './pages/Jobs'
import ManualReview from './pages/ManualReview'
import Overview from './pages/Overview'
import Queue from './pages/Queue'
import Recordings from './pages/Recordings'
import TokenAnalytics from './pages/TokenAnalytics'

const links = [
  ['/', 'Overview'],
  ['/jobs', 'Jobs'],
  ['/recordings', 'Recordings'],
  ['/tokens', 'Token Analytics'],
  ['/queue', 'Queue'],
  ['/manual', 'Manual Review'],
]

export default function App() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-6 md:px-6">
      <header className="mb-6 rounded-2xl border border-emerald-200 bg-white/90 p-5 shadow-sm backdrop-blur">
        <h1 className="text-2xl font-semibold">AI Job Application Agent</h1>
        <p className="text-sm text-slate-600">Automation, replay savings, and live operational telemetry.</p>
        <nav className="mt-4 flex flex-wrap gap-2">
          {links.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm ${isActive ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-700'}`
              }
              end={to === '/'}
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </header>

      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/recordings" element={<Recordings />} />
        <Route path="/tokens" element={<TokenAnalytics />} />
        <Route path="/queue" element={<Queue />} />
        <Route path="/manual" element={<ManualReview />} />
      </Routes>
    </div>
  )
}
