import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  fetchStats, fetchJobCountBySource,
  triggerSeekScrape, triggerIworkforsaScrape, triggerIndeedScrape,
  deleteJobsBySource, rescoreJobsBySource, fetchScrapeStatus, stopScrape,
} from '../api/client';
import {
  Briefcase, CheckCircle, TrendingUp, Star,
  Play, Loader, Trash2, RefreshCw, ArrowRight, Square,
} from 'lucide-react';

// ── Stat tile ────────────────────────────────────────────────────────────────

function StatTile({
  label, value, icon: Icon, iconBg, href,
}: {
  label:  string;
  value:  string | number;
  icon:   React.ElementType;
  iconBg: string;
  href:   string;
}) {
  const navigate = useNavigate();
  return (
    <button
      onClick={() => navigate(href)}
      className="group bg-white rounded-2xl p-5 text-left shadow-sm border border-gray-100 hover:shadow-md hover:border-gray-200 transition-all w-full"
    >
      <div className={`inline-flex items-center justify-center w-9 h-9 rounded-xl mb-4 ${iconBg}`}>
        <Icon size={17} />
      </div>
      <p className="text-3xl font-bold text-gray-900 tracking-tight">{value}</p>
      <div className="flex items-center justify-between mt-1">
        <p className="text-sm text-gray-500 font-medium">{label}</p>
        <ArrowRight size={13} className="text-gray-300 group-hover:text-gray-500 group-hover:translate-x-0.5 transition-all" />
      </div>
    </button>
  );
}

// ── Last run badge ────────────────────────────────────────────────────────────

function LastRunBadge({ result }: { result: Record<string, unknown> }) {
  if ('error' in result) {
    return (
      <div className="mt-4 flex items-center gap-1.5 text-xs text-red-600 bg-red-50 border border-red-100 rounded-xl px-3 py-2">
        <span className="w-1.5 h-1.5 bg-red-500 rounded-full shrink-0" />
        Last run failed — check backend logs
      </div>
    );
  }
  if ('inserted' in result) {
    const found    = result.found    as number ?? 0;
    const inserted = result.inserted as number ?? 0;
    const skipped  = result.skipped  as number ?? 0;
    const stopped  = result.stopped  as boolean ?? false;
    return (
      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
        {stopped && (
          <span className="px-2.5 py-1 bg-amber-50 text-amber-700 border border-amber-200 rounded-full font-medium">
            stopped early
          </span>
        )}
        <span className="px-2.5 py-1 bg-gray-100 text-gray-500 rounded-full">{found} found</span>
        <span className={`px-2.5 py-1 rounded-full font-medium ${inserted > 0 ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-gray-100 text-gray-400'}`}>
          +{inserted} new
        </span>
        <span className="px-2.5 py-1 bg-gray-100 text-gray-400 rounded-full">{skipped} skipped</span>
      </div>
    );
  }
  return null;
}

// ── Scrape card ───────────────────────────────────────────────────────────────

function ScrapeCard({
  title, source, description,
  isRunning, lastResult,
  onRun, onStop, onClear, onRescore, onViewJobs,
  clearing, rescoring,
  accentColor,
}: {
  title:       string;
  source:      string;
  description: string;
  isRunning:   boolean;
  lastResult:  Record<string, unknown>;
  onRun:       () => void;
  onStop:      () => void;
  onClear:     () => void;
  onRescore:   () => void;
  onViewJobs:  () => void;
  clearing:    boolean;
  rescoring:   boolean;
  accentColor: string;
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
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      {/* Card header */}
      <div className={`h-1 w-full ${accentColor}`} />
      <div className="p-5">
        <div className="flex items-start justify-between mb-1">
          <button
            onClick={onViewJobs}
            className="font-semibold text-gray-900 hover:text-violet-600 transition text-base"
          >
            {title}
          </button>
          {jobCount !== undefined && (
            <button
              onClick={onViewJobs}
              className="text-xs text-gray-400 hover:text-violet-600 flex items-center gap-1 transition font-medium"
            >
              {jobCount} job{jobCount !== 1 ? 's' : ''}
              <ArrowRight size={11} />
            </button>
          )}
        </div>
        <p className="text-sm text-gray-400 mb-4 leading-relaxed">{description}</p>

        {/* Status bar */}
        {isRunning && (
          <div className="mb-4 flex items-center gap-2 text-xs text-violet-600 bg-violet-50 border border-violet-100 rounded-xl px-3 py-2">
            <Loader size={12} className="animate-spin shrink-0" />
            Running — jobs found so far will be saved if you stop
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-wrap gap-2">
          {isRunning ? (
            <button
              onClick={onStop}
              className="flex items-center gap-1.5 bg-amber-500 text-white px-3.5 py-2 rounded-xl hover:bg-amber-600 transition text-xs font-medium"
            >
              <Square size={12} /> Stop
            </button>
          ) : (
            <button
              onClick={onRun}
              disabled={clearing || rescoring}
              className="flex items-center gap-1.5 bg-violet-600 text-white px-3.5 py-2 rounded-xl hover:bg-violet-700 disabled:opacity-50 transition text-xs font-medium"
            >
              <Play size={12} /> Run Now
            </button>
          )}
          <button
            onClick={onRescore}
            disabled={isRunning || clearing || rescoring || jobCount === 0}
            className="flex items-center gap-1.5 border border-gray-200 text-gray-600 px-3.5 py-2 rounded-xl hover:bg-gray-50 disabled:opacity-40 transition text-xs font-medium"
          >
            {rescoring ? <Loader size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            {rescoring ? 'Rescoring…' : 'Re-score'}
          </button>
          <button
            onClick={handleClearClick}
            disabled={isRunning || clearing || rescoring || jobCount === 0}
            className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-medium transition disabled:opacity-40 ${
              confirmClear
                ? 'bg-red-600 text-white hover:bg-red-700'
                : 'border border-red-200 text-red-500 hover:bg-red-50'
            }`}
          >
            {clearing ? <Loader size={12} className="animate-spin" /> : <Trash2 size={12} />}
            {clearing ? 'Clearing…' : confirmClear ? `Delete ${jobCount}?` : 'Clear'}
          </button>
        </div>

        {!isRunning && Object.keys(lastResult).length > 0 && (
          <LastRunBadge result={lastResult} />
        )}
      </div>
    </div>
  );
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

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

  const seekM  = useMutation({ mutationFn: () => triggerSeekScrape({ keywords: ['Software Engineer', 'Full Stack Developer', 'Java Developer', 'React Developer'], location: 'Adelaide', max_pages: 3 }), onSuccess: () => qc.invalidateQueries({ queryKey: ['scrapeStatus'] }) });
  const govM   = useMutation({ mutationFn: triggerIworkforsaScrape, onSuccess: () => qc.invalidateQueries({ queryKey: ['scrapeStatus'] }) });
  const indeedM = useMutation({ mutationFn: () => triggerIndeedScrape({ keywords: ['Software Engineer', 'Full Stack Developer', 'Java Developer', 'React Developer'], location: 'Adelaide SA', max_pages: 3 }), onSuccess: () => qc.invalidateQueries({ queryKey: ['scrapeStatus'] }) });

  function makeClearMutation(source: string) {
    return useMutation({ mutationFn: () => deleteJobsBySource(source), onSuccess: () => { qc.invalidateQueries({ queryKey: ['stats'] }); qc.invalidateQueries({ queryKey: ['jobs'] }); qc.invalidateQueries({ queryKey: ['jobCount', source] }); } });
  }
  function makeRescoreMutation(source: string) {
    return useMutation({ mutationFn: () => rescoreJobsBySource(source), onSuccess: () => { qc.invalidateQueries({ queryKey: ['jobs'] }); qc.invalidateQueries({ queryKey: ['stats'] }); } });
  }
  function makeStopMutation(source: string) {
    return useMutation({ mutationFn: () => stopScrape(source), onSuccess: () => qc.invalidateQueries({ queryKey: ['scrapeStatus'] }) });
  }

  const clearSeekM     = makeClearMutation('seek');
  const clearGovM      = makeClearMutation('iworkforsa');
  const clearIndeedM   = makeClearMutation('indeed');
  const rescoreSeekM   = makeRescoreMutation('seek');
  const rescoreGovM    = makeRescoreMutation('iworkforsa');
  const rescoreIndeedM = makeRescoreMutation('indeed');
  const stopSeekM      = makeStopMutation('seek');
  const stopGovM       = makeStopMutation('iworkforsa');
  const stopIndeedM    = makeStopMutation('indeed');

  const statTiles = [
    { label: 'Total Jobs',  value: stats?.total_jobs ?? 0,   icon: Briefcase,   iconBg: 'bg-blue-50 text-blue-600',    href: '/jobs' },
    { label: 'Applied',     value: stats?.applied_count ?? 0, icon: CheckCircle, iconBg: 'bg-emerald-50 text-emerald-600', href: '/jobs?applied=applied' },
    { label: 'High Match',  value: stats?.high_match ?? 0,   icon: Star,        iconBg: 'bg-amber-50 text-amber-600',   href: '/jobs?min=0.7&sort=match_score' },
    { label: 'Avg Score',   value: stats ? `${(stats.avg_score * 100).toFixed(0)}%` : '—', icon: TrendingUp, iconBg: 'bg-violet-50 text-violet-600', href: '/jobs?sort=match_score' },
  ];

  return (
    <div className="p-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Dashboard</h1>
        <p className="text-sm text-gray-400 mt-1">Overview of your job search progress</p>
      </div>

      {/* Stat tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {statTiles.map(t => <StatTile key={t.label} {...t} />)}
      </div>

      {/* Section heading */}
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">Sources</h2>
        <div className="flex-1 h-px bg-gray-200" />
      </div>

      {/* Scrape cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ScrapeCard
          title="Seek" source="seek" accentColor="bg-blue-500"
          description="Software Engineer, Full Stack, Java & React roles in Adelaide. Takes 20–30 min."
          isRunning={scrapeStatus?.seek.running ?? false}
          lastResult={scrapeStatus?.seek.last_result ?? {}}
          onRun={() => seekM.mutate()} onStop={() => stopSeekM.mutate()}
          onClear={() => clearSeekM.mutate()} onRescore={() => rescoreSeekM.mutate()}
          onViewJobs={() => navigate('/jobs?source=seek')}
          clearing={clearSeekM.isPending} rescoring={rescoreSeekM.isPending}
        />
        <ScrapeCard
          title="iWorkForSA" source="iworkforsa" accentColor="bg-emerald-500"
          description="ICT category from the SA Government jobs board. Takes 5–10 min."
          isRunning={scrapeStatus?.iworkforsa.running ?? false}
          lastResult={scrapeStatus?.iworkforsa.last_result ?? {}}
          onRun={() => govM.mutate()} onStop={() => stopGovM.mutate()}
          onClear={() => clearGovM.mutate()} onRescore={() => rescoreGovM.mutate()}
          onViewJobs={() => navigate('/jobs?source=iworkforsa')}
          clearing={clearGovM.isPending} rescoring={rescoreGovM.isPending}
        />
        <ScrapeCard
          title="Indeed" source="indeed" accentColor="bg-violet-500"
          description="Software Engineer, Full Stack, Java & React roles in Adelaide SA. Metadata only."
          isRunning={scrapeStatus?.indeed?.running ?? false}
          lastResult={scrapeStatus?.indeed?.last_result ?? {}}
          onRun={() => indeedM.mutate()} onStop={() => stopIndeedM.mutate()}
          onClear={() => clearIndeedM.mutate()} onRescore={() => rescoreIndeedM.mutate()}
          onViewJobs={() => navigate('/jobs?source=indeed')}
          clearing={clearIndeedM.isPending} rescoring={rescoreIndeedM.isPending}
        />
      </div>
    </div>
  );
}
