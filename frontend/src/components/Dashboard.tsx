import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchStats, triggerScrape } from '../api/client';
import { Briefcase, CheckCircle, TrendingUp, Star, Play, Loader } from 'lucide-react';

export default function Dashboard() {
  const qc = useQueryClient();
  const { data: stats } = useQuery({ queryKey: ['stats'], queryFn: fetchStats });
  const [scrapeMsg, setScrapeMsg] = useState('');

  const scrapeM = useMutation({
    mutationFn: () => triggerScrape({
      keywords:  ['Software Engineer', 'Full Stack Developer', 'Java Developer', 'React Developer'],
      location:  'Adelaide',
      max_pages: 3,
    }),
    onSuccess: (res) => {
      setScrapeMsg(res.message);
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['stats'] });
    },
    onError: () => setScrapeMsg('Scrape failed. Check backend logs.'),
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
      <div className="bg-white rounded-xl border p-5">
        <h2 className="font-semibold text-gray-700 mb-3">Run Scrape</h2>
        <p className="text-sm text-gray-500 mb-4">
          Scrapes Seek for Software Engineer, Full Stack Developer, Java Developer, and React Developer roles in Adelaide. Takes 3-5 minutes.
        </p>
        <button
          onClick={() => scrapeM.mutate()}
          disabled={scrapeM.isPending}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition"
        >
          {scrapeM.isPending ? <Loader size={16} className="animate-spin" /> : <Play size={16} />}
          {scrapeM.isPending ? 'Scraping...' : 'Run Scrape Now'}
        </button>
        {scrapeMsg && (
          <p className="mt-3 text-sm text-gray-600 bg-gray-50 rounded p-2">{scrapeMsg}</p>
        )}
      </div>
    </div>
  );
}
