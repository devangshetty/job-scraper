import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import Dashboard  from './components/Dashboard';
import JobList    from './components/JobList';
import JobDetail  from './components/JobDetail';
import ResumePage from './components/ResumePage';
import { LayoutDashboard, List, Loader, FileUser } from 'lucide-react';
import { fetchScrapeStatus } from './api/client';

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
});

const navCls = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition ${
    isActive ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-100'
  }`;

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

  const seekRunning   = data?.seek.running;
  const govRunning    = data?.iworkforsa.running;
  const indeedRunning = data?.indeed?.running;

  if (!seekRunning && !govRunning && !indeedRunning) return null;

  return (
    <div className="mx-2 mt-4 flex flex-col gap-1">
      {seekRunning && (
        <div className="flex items-center gap-2 bg-blue-50 text-blue-600 text-xs px-3 py-2 rounded-lg">
          <Loader size={13} className="animate-spin shrink-0" />
          <span>Seek scraping...</span>
        </div>
      )}
      {govRunning && (
        <div className="flex items-center gap-2 bg-orange-50 text-orange-600 text-xs px-3 py-2 rounded-lg">
          <Loader size={13} className="animate-spin shrink-0" />
          <span>iWorkForSA scraping...</span>
        </div>
      )}
      {indeedRunning && (
        <div className="flex items-center gap-2 bg-purple-50 text-purple-600 text-xs px-3 py-2 rounded-lg">
          <Loader size={13} className="animate-spin shrink-0" />
          <span>Indeed scraping...</span>
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <div className="min-h-screen bg-gray-50 flex">
          <aside className="w-52 bg-white border-r flex flex-col p-4 gap-1 fixed h-full">
            <p className="text-lg font-bold text-gray-800 mb-4 px-2">JobTracker</p>
            <NavLink to="/"       className={navCls}><LayoutDashboard size={16} />Dashboard</NavLink>
            <NavLink to="/jobs"   className={navCls}><List size={16} />Job Listings</NavLink>
            <NavLink to="/resume" className={navCls}><FileUser size={16} />Resume</NavLink>
            <ScrapeIndicator />
          </aside>
          <main className="ml-52 flex-1 overflow-y-auto">
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
