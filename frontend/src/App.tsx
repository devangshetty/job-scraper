import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Dashboard from './components/Dashboard';
import JobList   from './components/JobList';
import JobDetail from './components/JobDetail';
import { LayoutDashboard, List } from 'lucide-react';

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
});

const navCls = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition ${
    isActive ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-100'
  }`;

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <div className="min-h-screen bg-gray-50 flex">
          <aside className="w-52 bg-white border-r flex flex-col p-4 gap-1 fixed h-full">
            <p className="text-lg font-bold text-gray-800 mb-4 px-2">JobTracker</p>
            <NavLink to="/"     className={navCls}><LayoutDashboard size={16} />Dashboard</NavLink>
            <NavLink to="/jobs" className={navCls}><List size={16} />Job Listings</NavLink>
          </aside>
          <main className="ml-52 flex-1 overflow-y-auto">
            <Routes>
              <Route path="/"         element={<Dashboard />} />
              <Route path="/jobs"     element={<JobList />} />
              <Route path="/jobs/:id" element={<JobDetail />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
