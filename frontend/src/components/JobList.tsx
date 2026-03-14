import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { fetchJobs } from '../api/client';
import type { Job } from '../types';
import { MapPin, Building2, DollarSign, Calendar, ChevronLeft, ChevronRight } from 'lucide-react';

const SOURCE_TABS = [
  { key: 'all',        label: 'All Jobs' },
  { key: 'seek',       label: 'Seek' },
  { key: 'iworkforsa', label: 'iWorkForSA' },
];

function parseSkills(raw: string | string[]): string[] {
  if (Array.isArray(raw)) return raw;
  try { return JSON.parse(raw) ?? []; }
  catch { return []; }
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-xs text-gray-400">Unscored</span>;
  const pct = Math.round(score * 100);
  const cls = score >= 0.7 ? 'bg-green-100 text-green-700' :
              score >= 0.5 ? 'bg-yellow-100 text-yellow-700' :
                             'bg-red-100 text-red-700';
  return <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${cls}`}>{pct}%</span>;
}

export default function JobList() {
  const navigate    = useNavigate();
  const [source,    setSource]    = useState('all');
  const [minScore,  setMinScore]  = useState(0);
  const [search,    setSearch]    = useState('');
  const [applied,   setApplied]   = useState<string>('all');
  const [sortBy,    setSortBy]    = useState('match_score');
  const [page,      setPage]      = useState(1);

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

  function switchSource(key: string) {
    setSource(key);
    setPage(1);
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-800 mb-4">Job Listings</h1>

      {/* Source tabs */}
      <div className="flex gap-1 mb-5 border-b">
        {SOURCE_TABS.map(t => (
          <button
            key={t.key}
            onClick={() => switchSource(t.key)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition ${
              source === t.key
                ? 'bg-white border border-b-white border-gray-200 text-blue-600 -mb-px'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-3 mb-5">
        <input
          type="text"
          placeholder="Search title or company..."
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(1); }}
          className="border rounded-lg px-3 py-2 text-sm flex-1 min-w-[200px] focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
        <select value={sortBy} onChange={e => setSortBy(e.target.value)}
          className="border rounded-lg px-3 py-2 text-sm focus:outline-none">
          <option value="match_score">Sort: Score</option>
          <option value="scraped_at">Sort: Date Scraped</option>
        </select>
        <select value={applied} onChange={e => { setApplied(e.target.value); setPage(1); }}
          className="border rounded-lg px-3 py-2 text-sm focus:outline-none">
          <option value="all">All Jobs</option>
          <option value="not_applied">Not Applied</option>
          <option value="applied">Applied</option>
        </select>
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <label>Min Score:</label>
          <input type="range" min={0} max={0.9} step={0.1} value={minScore}
            onChange={e => { setMinScore(parseFloat(e.target.value)); setPage(1); }}
            className="w-24" />
          <span>{Math.round(minScore * 100)}%</span>
        </div>
      </div>

      <p className="text-sm text-gray-500 mb-3">{data?.total ?? 0} jobs found</p>

      {isLoading ? (
        <div className="text-center text-gray-400 py-12">Loading...</div>
      ) : (
        <div className="flex flex-col gap-3">
          {(data?.jobs ?? []).map((job: Job) => {
            const skills = parseSkills(job.matched_skills);
            return (
              <div key={job.id} onClick={() => navigate(`/jobs/${job.id}`)}
                className="bg-white border rounded-xl p-4 cursor-pointer hover:shadow-md hover:border-blue-300 transition">
                <div className="flex justify-between items-start">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-gray-800">{job.job_title}</h3>
                      {job.source && (
                        <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">
                          {job.source === 'iworkforsa' ? 'iWorkForSA' : 'Seek'}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-3 text-sm text-gray-500 mt-1">
                      <span className="flex items-center gap-1"><Building2 size={13} />{job.company}</span>
                      {job.location    && <span className="flex items-center gap-1"><MapPin size={13} />{job.location}</span>}
                      {job.salary      && <span className="flex items-center gap-1"><DollarSign size={13} />{job.salary}</span>}
                      {job.posted_date && <span className="flex items-center gap-1"><Calendar size={13} />{job.posted_date}</span>}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <ScoreBadge score={job.match_score} />
                    {job.is_applied && (
                      <span className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full">Applied</span>
                    )}
                  </div>
                </div>
                {skills.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {skills.slice(0, 6).map(s => (
                      <span key={s} className="text-xs bg-green-50 text-green-700 px-2 py-0.5 rounded">{s}</span>
                    ))}
                    {skills.length > 6 && (
                      <span className="text-xs text-gray-400">+{skills.length - 6} more</span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex justify-center items-center gap-3 mt-6">
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
            className="p-2 rounded border hover:bg-gray-50 disabled:opacity-40">
            <ChevronLeft size={16} />
          </button>
          <span className="text-sm text-gray-600">Page {page} of {totalPages}</span>
          <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
            className="p-2 rounded border hover:bg-gray-50 disabled:opacity-40">
            <ChevronRight size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
