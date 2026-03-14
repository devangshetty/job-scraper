import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchStats, triggerSeekScrape, triggerIworkforsaScrape, fetchScrapeStatus } from '../api/client';
import { Briefcase, CheckCircle, TrendingUp, Star, Play, Loader } from 'lucide-react';

function ScrapeCard({
  title,
  description,
  isRunning,
  lastResult,
  onRun,
}: {
  title:       string;
  description: string;
  isRunning:   boolean;
  lastResult:  Record<string, unknown>;
  onRun:       () => void;
}) {
  return (
    <div className="bg-white rounded-xl border p-5">
      <h2 className="font-semibold text-gray-700 mb-1">{title}</h2>
      <p className="text-sm text-gray-500 mb-4">{description}</p>
      <button
        onClick={onRun}
        disabled={isRunning}
        className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition"
      >
        {isRunning ? <Loader size={16} className="animate-spin" /> : <Play size={16} />}
        {isRunning ? 'Scraping...' : 'Run Now'}
      </button>
      {isRunning && (
        <p className="mt-3 text-sm text-blue-600 bg-blue-50 rounded p-2">Running in the background. You can navigate freely.</p>
      )}
      {!isRunning && lastResult && 'inserted' in lastResult && (
        <p className="mt-3 text-sm text-gray-600 bg-gray-50 rounded p-2">
          Last run: {lastResult.scraped as number} found, {lastResult.inserted as number} new jobs added.
        </p>
      )}
      {!isRunning && lastResult && 'error' in lastResult && (
        <p className="mt-3 text-sm text-red-600 bg-red-50 rounded p-2">Last run failed. Check backend logs.</p>
      )}
    </div>
  );
}

export default function Dashboard() {
  const qc                    = useQueryClient();
  const { data: stats }       = useQuery({ queryKey: ['stats'], queryFn: fetchStats });
  const { data: scrapeStatus } = useQuery({
    queryKey: ['scrapeStatus'],
    queryFn:  fetchScrapeStatus,
    refetchInterval: (query) => {
      const d = query.state.data;
      return (d?.seek.running || d?.iworkforsa.running) ? 3000 : false;
    },
    staleTime: 0,
  });

  const seekM = useMutation({
    mutationFn: () => triggerSeekScrape({
      keywords:  ['Software Engineer', 'Full Stack Developer', 'Java Developer', 'React Developer'],
      location:  'Adelaide',
      max_pages: 3,
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scrapeStatus'] }),
  });

  const govM = useMutation({
    mutationFn: triggerIworkforsaScrape,
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['scrapeStatus'] }),
  });

  const tiles = [
    { label: 'Total Jobs',  value: stats?.total_jobs    ?? 0,  icon: Briefcase,   color: 'bg-blue-50 text-blue-600' },
    { label: 'Applied',     value: stats?.applied_count ?? 0,  icon: CheckCircle, color: 'bg-green-50 text-green-600' },
    { label: 'High Match',  value: stats?.high_match    ?? 0,  icon: Star,        color: 'bg-yellow-50 text-yellow-600' },
    { label: 'Avg Score',   value: stats ? `${(stats.avg_score * 100).toFixed(0)}%` : '\u2014', icon: TrendingUp, color: 'bg-purple-50 text-purple-600' },
  ];

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-800 mb-6">Dashboard</h1>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {tiles.map(({ label, value, icon: Icon, color }) => (
          <div key={label} className={`rounded-xl p-4 ${color} flex flex-col gap-2`}>
            <Icon size={20} />
            <p className="text-2xl font-bold">{value}</p>
            <p className="text-sm font-medium">{label}</p>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ScrapeCard
          title="Seek"
          description="Scrapes Software Engineer, Full Stack Developer, Java Developer, and React Developer roles in Adelaide. Takes 20-30 min."
          isRunning={scrapeStatus?.seek.running ?? false}
          lastResult={scrapeStatus?.seek.last_result ?? {}}
          onRun={() => seekM.mutate()}
        />
        <ScrapeCard
          title="iworkforSA"
          description="Scrapes the Information/Communication Technology category from the SA Government jobs board. Takes 5-10 min."
          isRunning={scrapeStatus?.iworkforsa.running ?? false}
          lastResult={scrapeStatus?.iworkforsa.last_result ?? {}}
          onRun={() => govM.mutate()}
        />
      </div>
    </div>
  );
}
