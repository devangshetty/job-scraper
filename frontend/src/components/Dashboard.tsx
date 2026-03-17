import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  fetchStats,
  fetchJobCountBySource,
  triggerSeekScrape,
  triggerIworkforsaScrape,
  triggerIndeedScrape,
  deleteJobsBySource,
  rescoreJobsBySource,
  fetchScrapeStatus,
} from '../api/client';
import { Briefcase, CheckCircle, TrendingUp, Star, Play, Loader, Trash2, RefreshCw, ChevronRight } from 'lucide-react';

function LastRunBadge({ result }: { result: Record<string, unknown> }) {
  if ('error' in result) {
    return (
      <p className="mt-3 text-sm text-red-600 bg-red-50 rounded p-2">
        Last run failed. Check backend logs.
      </p>
    )
  }
  if ('inserted' in result) {
    const found    = result.found    as number ?? 0
    const inserted = result.inserted as number ?? 0
    const skipped  = result.skipped  as number ?? 0
    return (
      <div className="mt-3 flex gap-3 text-xs">
        <span className="px-2 py-1 bg-gray-100 text-gray-600 rounded-lg">
          {found} found
        </span>
        <span className={`px-2 py-1 rounded-lg ${
          inserted > 0 ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-400'
        }`}>
          {inserted} new
        </span>
        <span className="px-2 py-1 bg-gray-100 text-gray-400 rounded-lg">
          {skipped} skipped
        </span>
      </div>
    )
  }
  return null
}

function ScrapeCard({
  title,
  source,
  description,
  isRunning,
  lastResult,
  onRun,
  onClear,
  onRescore,
  onViewJobs,
  clearing,
  rescoring,
}: {
  title:       string;
  source:      string;
  description: string;
  isRunning:   boolean;
  lastResult:  Record<string, unknown>;
  onRun:       () => void;
  onClear:     () => void;
  onRescore:   () => void;
  onViewJobs:  () => void;
  clearing:    boolean;
  rescoring:   boolean;
}) {
  const [confirmClear, setConfirmClear] = useState(false);

  const { data: jobCount } = useQuery({
    queryKey: ['jobCount', source],
    queryFn:  () => fetchJobCountBySource(source),
    staleTime: 30_000,
  });

  function handleClearClick() {
    if (!confirmClear) {
      setConfirmClear(true);
      setTimeout(() => setConfirmClear(false), 3000);
    } else {
      setConfirmClear(false);
      onClear();
    }
  }

  return (
    <div className="bg-white rounded-xl border p-5">
      <div className="flex items-start justify-between mb-1">
        <button
          onClick={onViewJobs}
          className="font-semibold text-gray-700 hover:text-blue-600 flex items-center gap-1 transition group"
        >
          {title}
          <ChevronRight size={14} className="opacity-0 group-hover:opacity-100 transition" />
        </button>
        {jobCount !== undefined && (
          <button
            onClick={onViewJobs}
            className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full hover:bg-blue-50 hover:text-blue-600 transition"
          >
            {jobCount} job{jobCount !== 1 ? 's' : ''}
          </button>
        )}
      </div>
      <p className="text-sm text-gray-500 mb-4">{description}</p>
      <div className="flex flex-wrap gap-2">
        <button
          onClick={onRun}
          disabled={isRunning || clearing || rescoring}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition text-sm"
        >
          {isRunning ? <Loader size={15} className="animate-spin" /> : <Play size={15} />}
          {isRunning ? 'Scraping...' : 'Run Now'}
        </button>
        <button
          onClick={onRescore}
          disabled={isRunning || clearing || rescoring || jobCount === 0}
          className="flex items-center gap-2 border border-gray-300 text-gray-600 px-4 py-2 rounded-lg hover:bg-gray-50 disabled:opacity-40 transition text-sm"
        >
          {rescoring ? <Loader size={15} className="animate-spin" /> : <RefreshCw size={15} />}
          {rescoring ? 'Rescoring...' : 'Re-score'}
        </button>
        <button
          onClick={handleClearClick}
          disabled={isRunning || clearing || rescoring || jobCount === 0}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition disabled:opacity-40 ${
            confirmClear
              ? 'bg-red-600 text-white hover:bg-red-700'
              : 'border border-red-300 text-red-500 hover:bg-red-50'
          }`}
        >
          {clearing ? <Loader size={15} className="animate-spin" /> : <Trash2 size={15} />}
          {clearing
            ? 'Clearing...'
            : confirmClear
            ? `Delete ${jobCount} job${jobCount !== 1 ? 's' : ''}?`
            : 'Clear Jobs'}
        </button>
      </div>
      {isRunning && (
        <p className="mt-3 text-sm text-blue-600 bg-blue-50 rounded p-2">
          Running in the background. You can navigate freely.
        </p>
      )}
      {!isRunning && Object.keys(lastResult).length > 0 && (
        <LastRunBadge result={lastResult} />
      )}
    </div>
  );
}

export default function Dashboard() {
  const qc                     = useQueryClient();
  const navigate               = useNavigate();
  const { data: stats }        = useQuery({ queryKey: ['stats'], queryFn: fetchStats });
  const { data: scrapeStatus } = useQuery({
    queryKey: ['scrapeStatus'],
    queryFn:  fetchScrapeStatus,
    refetchInterval: (query) => {
      const d = query.state.data;
      return (d?.seek.running || d?.iworkforsa.running || d?.indeed?.running) ? 3000 : false;
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

  const indeedM = useMutation({
    mutationFn: () => triggerIndeedScrape({
      keywords:  ['Software Engineer', 'Full Stack Developer', 'Java Developer', 'React Developer'],
      location:  'Adelaide SA',
      max_pages: 3,
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scrapeStatus'] }),
  });

  function makeClearMutation(source: string) {
    return useMutation({
      mutationFn: () => deleteJobsBySource(source),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ['stats'] });
        qc.invalidateQueries({ queryKey: ['jobs'] });
        qc.invalidateQueries({ queryKey: ['jobCount', source] });
      },
    });
  }

  function makeRescoreMutation(source: string) {
    return useMutation({
      mutationFn: () => rescoreJobsBySource(source),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ['jobs'] });
        qc.invalidateQueries({ queryKey: ['stats'] });
      },
    });
  }

  const clearSeekM     = makeClearMutation('seek');
  const clearGovM      = makeClearMutation('iworkforsa');
  const clearIndeedM   = makeClearMutation('indeed');
  const rescoreSeekM   = makeRescoreMutation('seek');
  const rescoreGovM    = makeRescoreMutation('iworkforsa');
  const rescoreIndeedM = makeRescoreMutation('indeed');

  const tiles = [
    { label: 'Total Jobs',  value: stats?.total_jobs ?? 0,                           icon: Briefcase,   color: 'bg-blue-50 text-blue-600',   href: '/jobs' },
    { label: 'Applied',     value: stats?.applied_count ?? 0,                        icon: CheckCircle, color: 'bg-green-50 text-green-600',  href: '/jobs?applied=applied' },
    { label: 'High Match',  value: stats?.high_match ?? 0,                           icon: Star,        color: 'bg-yellow-50 text-yellow-600', href: '/jobs?min=0.7&sort=match_score' },
    { label: 'Avg Score',   value: stats ? `${(stats.avg_score * 100).toFixed(0)}%` : '\u2014', icon: TrendingUp, color: 'bg-purple-50 text-purple-600', href: '/jobs?sort=match_score' },
  ];

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-800 mb-6">Dashboard</h1>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {tiles.map(({ label, value, icon: Icon, color, href }) => (
          <button
            key={label}
            onClick={() => navigate(href)}
            className={`rounded-xl p-4 ${color} flex flex-col gap-2 text-left hover:opacity-80 transition cursor-pointer w-full`}
          >
            <Icon size={20} />
            <p className="text-2xl font-bold">{value}</p>
            <p className="text-sm font-medium">{label}</p>
          </button>
        ))}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ScrapeCard
          title="Seek"
          source="seek"
          description="Scrapes Software Engineer, Full Stack, Java and React roles in Adelaide. Takes 20-30 min."
          isRunning={scrapeStatus?.seek.running ?? false}
          lastResult={scrapeStatus?.seek.last_result ?? {}}
          onRun={() => seekM.mutate()}
          onClear={() => clearSeekM.mutate()}
          onRescore={() => rescoreSeekM.mutate()}
          onViewJobs={() => navigate('/jobs?source=seek')}
          clearing={clearSeekM.isPending}
          rescoring={rescoreSeekM.isPending}
        />
        <ScrapeCard
          title="iWorkForSA"
          source="iworkforsa"
          description="Scrapes the ICT category from the SA Government jobs board. Takes 5-10 min."
          isRunning={scrapeStatus?.iworkforsa.running ?? false}
          lastResult={scrapeStatus?.iworkforsa.last_result ?? {}}
          onRun={() => govM.mutate()}
          onClear={() => clearGovM.mutate()}
          onRescore={() => rescoreGovM.mutate()}
          onViewJobs={() => navigate('/jobs?source=iworkforsa')}
          clearing={clearGovM.isPending}
          rescoring={rescoreGovM.isPending}
        />
        <ScrapeCard
          title="Indeed"
          source="indeed"
          description="Scrapes Software Engineer, Full Stack, Java and React roles in Adelaide SA. Metadata only."
          isRunning={scrapeStatus?.indeed?.running ?? false}
          lastResult={scrapeStatus?.indeed?.last_result ?? {}}
          onRun={() => indeedM.mutate()}
          onClear={() => clearIndeedM.mutate()}
          onRescore={() => rescoreIndeedM.mutate()}
          onViewJobs={() => navigate('/jobs?source=indeed')}
          clearing={clearIndeedM.isPending}
          rescoring={rescoreIndeedM.isPending}
        />
      </div>
    </div>
  );
}
