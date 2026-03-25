import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import Dashboard  from './components/Dashboard';
import JobList    from './components/JobList';
import JobDetail  from './components/JobDetail';
import ResumePage from './components/ResumePage';
import { LayoutDashboard, Briefcase, FileText, Zap, Loader } from 'lucide-react';
import { fetchScrapeStatus } from './api/client';

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
});

const NAV_ITEMS = [
  { to: '/',       icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/jobs',   icon: Briefcase,       label: 'Jobs',      end: false },
  { to: '/resume', icon: FileText,        label: 'Resume',    end: false },
];

function ScrapeIndicator() {
  const { data } = useQuery({
    queryKey: ['scrapeStatus'],
    queryFn:  fetchScrapeStatus,
    refetchInterval: (query) => {
      const d = query.state.data;
      return (d?.seek.running || d?.iworkforsa.running || d?.indeed?.running) ? 3000 : false;
    },
    staleTime: 0,
  });

  const running = [
    data?.seek?.running       && 'Seek',
    data?.iworkforsa?.running && 'iWorkForSA',
    data?.indeed?.running     && 'Indeed',
  ].filter(Boolean) as string[];

  if (!running.length) return null;

  return (
    <div className="px-3 pb-4 flex flex-col gap-1.5">
      {running.map(src => (
        <div key={src} className="flex items-center gap-2 text-xs text-violet-300 bg-violet-500/10 px-3 py-2 rounded-lg border border-violet-500/20">
          <Loader size={11} className="animate-spin shrink-0" />
          <span>{src} scraping…</span>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <div className="min-h-screen bg-gray-50 flex">
          {/* Sidebar */}
          <aside className="w-56 bg-gray-900 flex flex-col fixed h-full z-10">
            {/* Logo */}
            <div className="px-4 h-14 flex items-center gap-2.5 border-b border-white/10 shrink-0">
              <div className="w-7 h-7 bg-violet-600 rounded-lg flex items-center justify-center shrink-0">
                <Zap size={14} className="text-white" />
              </div>
              <span className="text-white font-semibold tracking-tight text-sm">JobTracker</span>
            </div>

            {/* Nav */}
            <nav className="flex-1 px-2 py-3 flex flex-col gap-0.5">
              {NAV_ITEMS.map(({ to, icon: Icon, label, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                      isActive
                        ? 'bg-violet-600 text-white shadow-sm'
                        : 'text-gray-400 hover:text-white hover:bg-white/5'
                    }`
                  }
                >
                  <Icon size={15} />
                  {label}
                </NavLink>
              ))}
            </nav>

            {/* Running scrape indicators */}
            <ScrapeIndicator />

            {/* Footer */}
            <div className="px-4 py-3 border-t border-white/10">
              <p className="text-xs text-gray-600">Adelaide, SA · 2026</p>
            </div>
          </aside>

          {/* Content */}
          <main className="ml-56 flex-1 min-h-screen">
            <Routes>
              <Route path="/"         element={<Dashboard />} />
              <Route path="/jobs"     element={<JobList />} />
              <Route path="/jobs/:id" element={<JobDetail />} />
              <Route path="/resume"   element={<ResumePage />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
