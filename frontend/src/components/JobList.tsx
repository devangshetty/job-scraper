import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { fetchJobs } from '../api/client';
import type { Job } from '../types';
import { MapPin, Building2, DollarSign, Calendar, ChevronLeft, ChevronRight, Clock, Search, SlidersHorizontal } from 'lucide-react';

// ── Helpers ───────────────────────────────────────────────────────────────────

function parseSkills(raw: string | string[]): string[] {
  if (Array.isArray(raw)) return raw;
  try { return JSON.parse(raw) ?? []; }
  catch { return []; }
}

function formatScrapedAt(raw: string): string {
  if (!raw) return '';
  const d = new Date(raw.endsWith('Z') ? raw : raw + 'Z');
  if (isNaN(d.getTime())) return '';
  const now      = new Date();
  const diffMs   = now.getTime() - d.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHrs  = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHrs / 24);
  if (diffMins < 1)   return 'just now';
  if (diffMins < 60)  return `${diffMins}m ago`;
  if (diffHrs < 24)   return `${diffHrs}h ago`;
  if (diffDays === 1) return 'yesterday';
  if (diffDays < 7)   return `${diffDays}d ago`;
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' });
}

function scrapedDateLabel(raw: string | null | undefined): string {
  if (!raw) return 'Unknown date';
  const d = new Date(raw.endsWith('Z') ? raw : raw + 'Z');
  if (isNaN(d.getTime())) return 'Unknown date';
  const now     = new Date();
  const today   = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const jobDay  = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diffDays = Math.round((today.getTime() - jobDay.getTime()) / 86400000);
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7)   return d.toLocaleDateString('en-AU', { weekday: 'long' });
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'long', year: 'numeric' });
}

function DateDivider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 py-1 px-1">
      <div className="flex-1 h-px bg-gray-200" />
      <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider whitespace-nowrap">{label}</span>
      <div className="flex-1 h-px bg-gray-200" />
    </div>
  );
}

// ── Score badge ───────────────────────────────────────────────────────────────

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return (
    <span className="text-xs font-medium text-gray-400 bg-gray-100 px-2.5 py-1 rounded-full">—</span>
  );
  const pct = Math.round(score * 100);
  const cls  = score >= 0.7 ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' :
               score >= 0.5 ? 'bg-amber-50 text-amber-700 border border-amber-200' :
                              'bg-red-50 text-red-600 border border-red-200';
  return <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${cls}`}>{pct}%</span>;
}

// ── Source config ─────────────────────────────────────────────────────────────

const SOURCE_TABS = [
  { key: 'all',        label: 'All' },
  { key: 'seek',       label: 'Seek' },
  { key: 'indeed',     label: 'Indeed' },
  { key: 'iworkforsa', label: 'iWorkForSA' },
];

const SOURCE_COLORS: Record<string, string> = {
  seek:       'bg-blue-50 text-blue-600 border border-blue-100',
  indeed:     'bg-violet-50 text-violet-600 border border-violet-100',
  iworkforsa: 'bg-emerald-50 text-emerald-700 border border-emerald-100',
};

// ── JobList ───────────────────────────────────────────────────────────────────

export default function JobList() {
  const navigate             = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const source   = searchParams.get('source')   ?? 'all';
  const search   = searchParams.get('search')   ?? '';
  const applied  = searchParams.get('applied')  ?? 'all';
  const sortBy   = searchParams.get('sort')     ?? 'match_score';
  const minScore = parseFloat(searchParams.get('min') ?? '0');
  const page     = parseInt(searchParams.get('page') ?? '1', 10);

  function setParam(updates: Record<string, string>) {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      Object.entries(updates).forEach(([k, v]) => {
        if (v === '' || v === 'all' || (v === '0' && k === 'min') || (v === '1' && k === 'page') || (v === 'match_score' && k === 'sort')) {
          next.delete(k);
        } else {
          next.set(k, v);
        }
      });
      return next;
    }, { replace: false });
  }

  const appliedFilter = applied === 'applied' ? true : applied === 'not_applied' ? false : undefined;

  const { data, isLoading } = useQuery({
    queryKey: ['jobs', source, minScore, search, applied, sortBy, page],
    queryFn:  () => fetchJobs({
      min_score:  minScore,
      search:     search || undefined,
      is_applied: appliedFilter,
      sort_by:    sortBy,
      sort_order: 'desc',
      source:     source === 'all' ? undefined : source,
      page,
      page_size:  20,
    }),
  });

  const totalPages = data ? Math.ceil(data.total / 20) : 1;

  return (
    <div className="p-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Jobs</h1>
        <p className="text-sm text-gray-400 mt-1">
          {data?.total ?? 0} listings scraped from Seek, Indeed & iWorkForSA
        </p>
      </div>

      {/* Source tabs */}
      <div className="flex gap-1 mb-5">
        {SOURCE_TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setParam({ source: t.key, page: '1' })}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${
              source === t.key
                ? 'bg-violet-600 text-white shadow-sm'
                : 'bg-white text-gray-500 border border-gray-200 hover:border-gray-300 hover:text-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap gap-2.5 mb-6">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search title or company…"
            value={search}
            onChange={e => setParam({ search: e.target.value, page: '1' })}
            className="w-full pl-9 pr-4 py-2.5 text-sm bg-white border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-transparent"
          />
        </div>
        <select
          value={sortBy}
          onChange={e => setParam({ sort: e.target.value })}
          className="px-3 py-2.5 text-sm bg-white border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-violet-400 cursor-pointer"
        >
          <option value="match_score">Sort: Best Match</option>
          <option value="scraped_at">Sort: Recently Scraped</option>
        </select>
        <select
          value={applied}
          onChange={e => setParam({ applied: e.target.value, page: '1' })}
          className="px-3 py-2.5 text-sm bg-white border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-violet-400 cursor-pointer"
        >
          <option value="all">All Jobs</option>
          <option value="not_applied">Not Applied</option>
          <option value="applied">Applied</option>
        </select>
        <div className="flex items-center gap-2.5 bg-white border border-gray-200 rounded-xl px-3 py-2.5">
          <SlidersHorizontal size={14} className="text-gray-400 shrink-0" />
          <input
            type="range" min={0} max={0.9} step={0.1} value={minScore}
            onChange={e => setParam({ min: e.target.value, page: '1' })}
            className="w-20 accent-violet-600"
          />
          <span className="text-sm text-gray-600 font-medium w-8 shrink-0">{Math.round(minScore * 100)}%</span>
        </div>
      </div>

      {/* List */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20 text-gray-400 text-sm gap-2">
          <div className="w-4 h-4 border-2 border-gray-300 border-t-violet-600 rounded-full animate-spin" />
          Loading jobs…
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {(() => {
            const jobs = data?.jobs ?? [];
            let lastLabel = '';
            const items: React.ReactNode[] = [];

            jobs.forEach((job: Job) => {
              if (sortBy === 'scraped_at') {
                const label = scrapedDateLabel(job.scraped_at);
                if (label !== lastLabel) {
                  items.push(<DateDivider key={`div-${label}-${job.id}`} label={label} />);
                  lastLabel = label;
                }
              }

              const skills      = parseSkills(job.matched_skills);
              const sourceLabel = job.source === 'iworkforsa' ? 'iWorkForSA' : job.source === 'indeed' ? 'Indeed' : job.source === 'seek' ? 'Seek' : job.source ?? '';
              const sourceCls   = SOURCE_COLORS[job.source ?? ''] ?? 'bg-gray-100 text-gray-500';

              items.push(
                <div
                  key={job.id}
                  onClick={() => navigate(`/jobs/${job.id}`)}
                  className="group bg-white border border-gray-100 rounded-2xl p-5 cursor-pointer hover:shadow-md hover:border-gray-200 transition-all"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-semibold text-gray-900 group-hover:text-violet-700 transition text-base leading-snug">
                          {job.job_title}
                        </h3>
                        {job.source && (
                          <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 font-medium ${sourceCls}`}>
                            {sourceLabel}
                          </span>
                        )}
                        {job.is_applied && (
                          <span className="text-xs bg-blue-50 text-blue-600 border border-blue-100 px-2 py-0.5 rounded-full shrink-0 font-medium">
                            Applied
                          </span>
                        )}
                      </div>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-gray-500">
                        <span className="flex items-center gap-1.5"><Building2 size={12} className="text-gray-400" />{job.company}</span>
                        {job.location    && <span className="flex items-center gap-1.5"><MapPin size={12} className="text-gray-400" />{job.location}</span>}
                        {job.salary      && <span className="flex items-center gap-1.5"><DollarSign size={12} className="text-gray-400" />{job.salary}</span>}
                        {job.posted_date && <span className="flex items-center gap-1.5"><Calendar size={12} className="text-gray-400" />{job.posted_date}</span>}
                        {sortBy === 'scraped_at' && job.scraped_at && (
                          <span className="flex items-center gap-1.5 text-violet-500">
                            <Clock size={12} />scraped {formatScrapedAt(job.scraped_at)}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="shrink-0 pt-0.5">
                      <ScoreBadge score={job.match_score} />
                    </div>
                  </div>

                  {skills.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-gray-50">
                      {skills.slice(0, 6).map(s => (
                        <span key={s} className="text-xs bg-gray-50 text-gray-600 border border-gray-100 px-2 py-0.5 rounded-lg">
                          {s}
                        </span>
                      ))}
                      {skills.length > 6 && (
                        <span className="text-xs text-gray-400 px-1 py-0.5">+{skills.length - 6} more</span>
                      )}
                    </div>
                  )}
                </div>
              );
            });

            if (items.length === 0) {
              return (
                <div className="text-center py-20 text-gray-400">
                  <p className="text-sm">No jobs found. Try adjusting your filters or run a scrape.</p>
                </div>
              );
            }

            return items;
          })()}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center items-center gap-3 mt-8">
          <button
            onClick={() => setParam({ page: String(page - 1) })}
            disabled={page === 1}
            className="p-2 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-40 transition"
          >
            <ChevronLeft size={15} />
          </button>
          <span className="text-sm text-gray-500 font-medium">Page {page} of {totalPages}</span>
          <button
            onClick={() => setParam({ page: String(page + 1) })}
            disabled={page === totalPages}
            className="p-2 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-40 transition"
          >
            <ChevronRight size={15} />
          </button>
        </div>
      )}
    </div>
  );
}
