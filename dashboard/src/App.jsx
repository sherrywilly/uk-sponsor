import { useMemo, useState } from 'react'
import Overview from './pages/Overview'
import Jobs from './pages/Jobs'
import Recordings from './pages/Recordings'
import TokenAnalytics from './pages/TokenAnalytics'
import Queue from './pages/Queue'
import ManualReview from './pages/ManualReview'

const PAGES = {
  overview: Overview,
  jobs: Jobs,
  recordings: Recordings,
  tokens: TokenAnalytics,
  queue: Queue,
  manual: ManualReview,
}

export default function App() {
  const [activePage, setActivePage] = useState('overview')
  const CurrentPage = useMemo(() => PAGES[activePage], [activePage])

  const nav = [
    ['overview', 'Overview'],
    ['jobs', 'Jobs'],
    ['recordings', 'Recordings'],
    ['tokens', 'Token Analytics'],
    ['queue', 'Queue'],
    ['manual', 'Manual Review'],
  ]

  return (
    <div className="mx-auto max-w-7xl px-3 py-6 md:px-6">
      <header className="mb-6 card px-4 py-4 md:px-6">
        <h1 className="text-2xl font-bold md:text-3xl">AI Job Application Agent</h1>
        <p className="mt-2 text-slate-600">Replay-first automation with token and cost visibility.</p>
        <nav className="mt-4 flex flex-wrap gap-2">
          {nav.map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setActivePage(id)}
              className={`rounded-md border px-3 py-1.5 text-sm font-semibold ${
                activePage === id
                  ? 'border-teal-700 bg-teal-700 text-white'
                  : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
              }`}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      <main>
        <CurrentPage />
      </main>
    </div>
  )
}
