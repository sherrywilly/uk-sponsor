import { NavLink, Route, Routes } from 'react-router-dom'
import Overview from './pages/Overview'
import Jobs from './pages/Jobs'
import Recordings from './pages/Recordings'
import TokenAnalytics from './pages/TokenAnalytics'
import Queue from './pages/Queue'
import ManualReview from './pages/ManualReview'

const tabs = [
  ['/', 'Overview'],
  ['/jobs', 'Jobs'],
  ['/recordings', 'Recordings'],
  ['/tokens', 'Token Analytics'],
  ['/queue', 'Queue'],
  ['/manual-review', 'Manual Review'],
]

export default function App() {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_#f5f7ff,_#edf2f7_55%,_#f7fafc)] text-slate-900">
      <div className="mx-auto max-w-7xl px-6 py-8">
        <header className="mb-8 rounded-2xl border border-slate-200 bg-white/80 p-5 shadow-sm backdrop-blur">
          <h1 className="font-['Space_Grotesk'] text-3xl font-bold">AI Job Application Agent</h1>
          <p className="text-sm text-slate-600">Replay-first browser automation with live token and cost analytics.</p>
          <nav className="mt-4 flex flex-wrap gap-2">
            {tabs.map(([to, label]) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `rounded-full px-4 py-1.5 text-sm font-semibold transition ${isActive ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`
                }
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
          <Route path="/manual-review" element={<ManualReview />} />
        </Routes>
      </div>
    </div>
  )
}
