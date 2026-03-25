import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchJob, updateJob, runGapAnalysis, fetchGapModelSettings, setGapModel, agentSearch, proxyDownloadUrl } from '../api/client';
import {
  ArrowLeft, ExternalLink, CheckCircle, Circle, Zap, AlertTriangle,
  Info, Lightbulb, ChevronDown, Users, Loader, Paperclip, Download,
  MapPin, Building2, DollarSign, Calendar,
} from 'lucide-react';

function parseSkills(raw: string | string[]): string[] {
  if (Array.isArray(raw)) return raw;
  try { return JSON.parse(raw) ?? []; }
  catch { return []; }
}

function applyButtonLabel(source: string | null | undefined): string {
  switch (source) {
    case 'iworkforsa': return 'Apply on iWorkForSA';
    case 'indeed':     return 'Apply on Indeed';
    case 'seek':       return 'Apply on Seek';
    default:           return 'Apply Now';
  }
}

const SOURCE_COLORS: Record<string, string> = {
  seek:       'bg-blue-50 text-blue-600 border border-blue-100',
  indeed:     'bg-violet-50 text-violet-600 border border-violet-100',
  iworkforsa: 'bg-emerald-50 text-emerald-700 border border-emerald-100',
};

// ── Gap Analysis Panel ────────────────────────────────────────────────────────

const VERDICT_STYLES: Record<string, { bar: string; badge: string }> = {
  'Strong Match':  { bar: 'bg-emerald-500', badge: 'bg-emerald-50 text-emerald-700 border border-emerald-200' },
  'Good Match':    { bar: 'bg-blue-500',    badge: 'bg-blue-50 text-blue-700 border border-blue-200' },
  'Partial Match': { bar: 'bg-amber-500',   badge: 'bg-amber-50 text-amber-700 border border-amber-200' },
  'Weak Match':    { bar: 'bg-red-500',     badge: 'bg-red-50 text-red-600 border border-red-200' },
};

function GapAnalysisPanel({ jobId }: { jobId: number }) {
  const qc = useQueryClient();
  const [result, setResult]       = useState<Record<string, unknown> | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);

  const { data: modelData } = useQuery({ queryKey: ['gapModel'], queryFn: fetchGapModelSettings, staleTime: 30_000 });
  const activeModel = selectedModel ?? modelData?.current_model ?? 'llama-3.1-8b-instant';

  const mutation = useMutation({
    mutationFn: async () => {
      if (selectedModel && selectedModel !== modelData?.current_model) {
        await setGapModel(selectedModel);
        qc.invalidateQueries({ queryKey: ['gapModel'] });
      }
      return runGapAnalysis(jobId);
    },
    onSuccess: (data) => setResult(data),
  });

  const running      = mutation.isPending;
  const error        = mutation.error?.message ?? null;
  const verdictKey   = result ? (result.match_verdict as string) : null;
  const verdictStyle = verdictKey ? (VERDICT_STYLES[verdictKey] ?? { bar: 'bg-gray-300', badge: 'bg-gray-100 text-gray-600' }) : null;

  return (
    <div className="mt-6 bg-white border border-gray-100 rounded-2xl overflow-hidden shadow-sm">
      {verdictStyle && <div className={`h-0.5 w-full ${verdictStyle.bar}`} />}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-50">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 bg-violet-50 rounded-lg flex items-center justify-center">
            <Zap size={13} className="text-violet-600" />
          </div>
          <span className="text-sm font-semibold text-gray-800">AI Gap Analysis</span>
          {verdictKey && verdictStyle && (
            <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium border ${verdictStyle.badge}`}>
              {verdictKey}
            </span>
          )}
        </div>
        {modelData && (
          <div className="flex items-center gap-2">
            <div className="relative">
              <select
                value={activeModel}
                onChange={e => setSelectedModel(e.target.value)}
                className="text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 pr-7 bg-white text-gray-600 appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-violet-400"
              >
                {modelData.available_models.map((m: { id: string; label: string }) => (
                  <option key={m.id} value={m.id}>{m.label}</option>
                ))}
              </select>
              <ChevronDown size={11} className="absolute right-2 top-2.5 text-gray-400 pointer-events-none" />
            </div>
            <button
              onClick={() => mutation.mutate()}
              disabled={running}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 text-white text-xs font-medium rounded-lg hover:bg-violet-700 disabled:opacity-50 transition"
            >
              {running ? 'Analysing…' : result ? 'Re-run' : 'Run Analysis'}
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="px-5 py-3 bg-red-50 text-sm text-red-600 border-b border-red-100">{error}</div>
      )}

      {running && (
        <div className="px-5 py-8 text-center text-sm text-gray-400 flex items-center justify-center gap-2">
          <div className="w-4 h-4 border-2 border-gray-200 border-t-violet-600 rounded-full animate-spin" />
          Calling Groq API — usually takes 2–5 seconds…
        </div>
      )}

      {result && !running && (
        <div className="p-5 flex flex-col gap-4">
          <p className="text-sm text-gray-700 leading-relaxed">{result.summary as string}</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <p className="text-xs font-semibold text-emerald-700 flex items-center gap-1.5 mb-2">
                <CheckCircle size={12} /> You have
              </p>
              <div className="flex flex-wrap gap-1.5">
                {(result.you_have as string[]).map(s => (
                  <span key={s} className="text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-lg">{s}</span>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-semibold text-red-600 flex items-center gap-1.5 mb-2">
                <AlertTriangle size={12} /> You are missing
              </p>
              <div className="flex flex-wrap gap-1.5">
                {(result.you_are_missing as string[]).map(s => (
                  <span key={s} className="text-xs bg-red-50 text-red-600 border border-red-200 px-2 py-0.5 rounded-lg">{s}</span>
                ))}
                {(result.you_are_missing as string[]).length === 0 && (
                  <span className="text-xs text-gray-400">Nothing significant</span>
                )}
              </div>
            </div>
          </div>
          {(result.you_can_claim as string[]).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-blue-600 flex items-center gap-1.5 mb-2">
                <Lightbulb size={12} /> Highlight in cover letter
              </p>
              <div className="flex flex-wrap gap-1.5">
                {(result.you_can_claim as string[]).map(s => (
                  <span key={s} className="text-xs bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded-lg">{s}</span>
                ))}
              </div>
            </div>
          )}
          {(result.red_flags as string[]).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-amber-600 flex items-center gap-1.5 mb-2">
                <Info size={12} /> Red flags
              </p>
              <ul className="list-disc list-inside space-y-0.5">
                {(result.red_flags as string[]).map(s => (
                  <li key={s} className="text-xs text-amber-700">{s}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {!result && !running && !error && (
        <div className="px-5 py-8 text-center text-sm text-gray-400">
          Select a model and click <strong className="text-gray-600">Run Analysis</strong> for an AI-powered gap analysis.
        </div>
      )}
    </div>
  );
}

// ── Research Panel ────────────────────────────────────────────────────────────

interface SearchResult { title: string; url: string; snippet: string; }

function parseContact(result: SearchResult): { name: string; role: string } {
  const withoutLinkedIn = result.title.replace(/\s*\|\s*LinkedIn.*$/i, '').trim();
  const dashIdx = withoutLinkedIn.indexOf(' - ');
  if (dashIdx !== -1) {
    return { name: withoutLinkedIn.slice(0, dashIdx).trim(), role: withoutLinkedIn.slice(dashIdx + 3).trim() };
  }
  return { name: withoutLinkedIn, role: '' };
}

function ResearchPanel({ company }: { company: string; location?: string | null }) {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [hasRun, setHasRun]   = useState(false);

  async function handleSearch() {
    setLoading(true);
    setError(null);
    try {
      const data     = await agentSearch(`"${company}" linkedin.com/in`, 10);
      const profiles = (data.results as SearchResult[]).filter(r => r.url.includes('linkedin.com/in/'));
      setResults(profiles);
      setHasRun(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Search failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mt-6 bg-white border border-gray-100 rounded-2xl overflow-hidden shadow-sm">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-50">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 bg-blue-50 rounded-lg flex items-center justify-center">
            <Users size={13} className="text-blue-600" />
          </div>
          <span className="text-sm font-semibold text-gray-800">People at {company}</span>
        </div>
        <button
          onClick={handleSearch}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition"
        >
          {loading ? <Loader size={12} className="animate-spin" /> : <Users size={12} />}
          {loading ? 'Searching…' : hasRun ? 'Search Again' : 'Find People'}
        </button>
      </div>

      {loading && (
        <div className="px-5 py-8 text-center text-sm text-gray-400 flex items-center justify-center gap-2">
          <div className="w-4 h-4 border-2 border-gray-200 border-t-blue-600 rounded-full animate-spin" />
          Searching LinkedIn profiles for {company}…
        </div>
      )}
      {error && !loading && (
        <div className="px-5 py-3 text-sm text-red-600 bg-red-50">{error}</div>
      )}
      {!loading && hasRun && results.length === 0 && (
        <div className="px-5 py-8 text-center text-sm text-gray-400">No LinkedIn profiles found.</div>
      )}
      {!loading && results.length > 0 && (
        <div className="divide-y divide-gray-50">
          {results.map((r, i) => {
            const { name, role } = parseContact(r);
            return (
              <div key={i} className="flex items-center justify-between px-5 py-3.5 gap-4 hover:bg-gray-50 transition">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">{name}</p>
                  {role && <p className="text-xs text-gray-400 mt-0.5 truncate">{role}</p>}
                  {r.snippet && <p className="text-xs text-gray-400 mt-1 line-clamp-1">{r.snippet}</p>}
                </div>
                <a
                  href={r.url} target="_blank" rel="noopener noreferrer"
                  className="shrink-0 flex items-center gap-1 text-xs bg-blue-50 text-blue-600 px-3 py-1.5 rounded-lg hover:bg-blue-100 transition font-medium"
                >
                  <ExternalLink size={11} /> Open
                </a>
              </div>
            );
          })}
        </div>
      )}
      {!loading && !hasRun && (
        <div className="px-5 py-6 text-center text-sm text-gray-400">
          Click <strong className="text-gray-600">Find People</strong> to search LinkedIn profiles at {company}.
        </div>
      )}
    </div>
  );
}

// ── JobDetail ─────────────────────────────────────────────────────────────────

export default function JobDetail() {
  const { id }   = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc       = useQueryClient();
  const jobId    = parseInt(id ?? '0');

  const { data: job, isLoading } = useQuery({
    queryKey: ['job', jobId],
    queryFn:  () => fetchJob(jobId),
    enabled:  !!jobId,
  });

  const [notes, setNotes] = useState('');
  useEffect(() => { if (job) setNotes(job.notes ?? ''); }, [job]);

  const updateM = useMutation({
    mutationFn: (update: { is_applied?: boolean; notes?: string }) => updateJob(jobId, update),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['job', jobId] });
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['stats'] });
    },
  });

  if (isLoading) return (
    <div className="flex items-center justify-center py-24 text-gray-400 text-sm gap-2">
      <div className="w-4 h-4 border-2 border-gray-200 border-t-violet-600 rounded-full animate-spin" />
      Loading…
    </div>
  );
  if (!job) return <div className="p-8 text-red-500 text-sm">Job not found.</div>;

  const matchedSkills  = parseSkills(job.matched_skills);
  const missingSkills  = parseSkills(job.missing_skills);
  const isIndeed       = job.source === 'indeed';
  const hasDescription = !!job.description && job.description.length > 80;
  const sourceCls      = SOURCE_COLORS[job.source ?? ''] ?? 'bg-gray-100 text-gray-500';
  const sourceLabel    = job.source === 'iworkforsa' ? 'iWorkForSA' : job.source === 'indeed' ? 'Indeed' : job.source === 'seek' ? 'Seek' : job.source ?? '';

  const scoreColor = !job.match_score ? 'text-gray-400' :
                     job.match_score >= 0.7 ? 'text-emerald-600' :
                     job.match_score >= 0.5 ? 'text-amber-500' : 'text-red-500';

  let attachments: { name: string; url: string }[] = [];
  try { attachments = JSON.parse((job as Record<string, string>).attachments || '[]'); } catch { /* empty */ }

  return (
    <div className="p-8 max-w-3xl mx-auto">
      {/* Back */}
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-700 mb-6 transition"
      >
        <ArrowLeft size={14} /> Back to Jobs
      </button>

      {/* Main card */}
      <div className="bg-white border border-gray-100 rounded-2xl shadow-sm overflow-hidden">
        {/* Score accent bar */}
        <div className={`h-1 w-full ${
          !job.match_score ? 'bg-gray-200' :
          job.match_score >= 0.7 ? 'bg-emerald-500' :
          job.match_score >= 0.5 ? 'bg-amber-400' : 'bg-red-400'
        }`} />

        <div className="p-6">
          {/* Header */}
          <div className="flex items-start justify-between gap-4 mb-4">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap mb-2">
                {job.source && (
                  <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${sourceCls}`}>{sourceLabel}</span>
                )}
                {job.is_applied && (
                  <span className="text-xs bg-blue-50 text-blue-600 border border-blue-100 px-2.5 py-0.5 rounded-full font-medium">Applied</span>
                )}
              </div>
              <h1 className="text-xl font-bold text-gray-900 tracking-tight leading-snug">{job.job_title}</h1>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-sm text-gray-500">
                <span className="flex items-center gap-1.5"><Building2 size={13} className="text-gray-400" />{job.company}</span>
                {job.location    && <span className="flex items-center gap-1.5"><MapPin size={13} className="text-gray-400" />{job.location}</span>}
                {job.salary      && <span className="flex items-center gap-1.5"><DollarSign size={13} className="text-gray-400" />{job.salary}</span>}
                {job.posted_date && <span className="flex items-center gap-1.5"><Calendar size={13} className="text-gray-400" />Posted {job.posted_date}</span>}
              </div>
            </div>
            {job.match_score !== null && (
              <div className="text-right shrink-0">
                <p className={`text-4xl font-bold tracking-tight ${scoreColor}`}>
                  {Math.round((job.match_score ?? 0) * 100)}%
                </p>
                <p className="text-xs text-gray-400 mt-0.5">match</p>
              </div>
            )}
          </div>

          {/* Indeed notice */}
          {isIndeed && (
            <div className="mb-5 p-3.5 bg-violet-50 border border-violet-100 rounded-xl text-sm text-violet-700">
              Indeed limits automated access to full job descriptions. Match score is based on the short snippet only.
              Click <strong>Apply on Indeed</strong> below to view the full listing.
            </div>
          )}

          {/* Skills */}
          {!isIndeed && hasDescription && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-5">
              <div>
                <p className="text-xs font-semibold text-emerald-700 flex items-center gap-1.5 mb-2">
                  <CheckCircle size={11} /> Matched Skills
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {matchedSkills.length > 0
                    ? matchedSkills.map(s => (
                        <span key={s} className="text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-lg">{s}</span>
                      ))
                    : <span className="text-xs text-gray-400">None detected</span>
                  }
                </div>
              </div>
              <div>
                <p className="text-xs font-semibold text-red-600 flex items-center gap-1.5 mb-2">
                  <AlertTriangle size={11} /> Missing Skills
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {missingSkills.slice(0, 10).map(s => (
                    <span key={s} className="text-xs bg-red-50 text-red-600 border border-red-200 px-2 py-0.5 rounded-lg">{s}</span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {!isIndeed && !hasDescription && (
            <div className="mb-5 p-3.5 bg-amber-50 border border-amber-100 rounded-xl text-sm text-amber-700">
              No description was scraped for this job. Skills and match score may not be accurate.
            </div>
          )}

          {/* Description */}
          <div className="mb-2">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              {isIndeed ? 'Snippet' : 'Job Description'}
            </p>
            <div className="text-sm text-gray-700 whitespace-pre-wrap bg-gray-50 rounded-xl p-4 max-h-80 overflow-y-auto leading-relaxed border border-gray-100">
              {job.description || 'No description available.'}
            </div>
          </div>
        </div>
      </div>

      {/* Gap Analysis */}
      {!isIndeed && hasDescription && <GapAnalysisPanel jobId={jobId} />}

      {/* Attachments */}
      {job.source === 'iworkforsa' && attachments.length > 0 && (
        <div className="mt-6 bg-white border border-gray-100 rounded-2xl overflow-hidden shadow-sm">
          <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-50">
            <div className="w-7 h-7 bg-gray-50 rounded-lg flex items-center justify-center">
              <Paperclip size={13} className="text-gray-500" />
            </div>
            <span className="text-sm font-semibold text-gray-800">Attachments</span>
          </div>
          <div className="divide-y divide-gray-50">
            {attachments.map((a, i) => (
              <div key={i} className="flex items-center justify-between px-5 py-3.5 gap-4 hover:bg-gray-50 transition">
                <span className="text-sm text-gray-700 truncate">{a.name}</span>
                <a
                  href={proxyDownloadUrl(a.url)}
                  download
                  className="shrink-0 flex items-center gap-1.5 text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-1.5 rounded-lg transition font-medium"
                >
                  <Download size={12} /> Download
                </a>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* People / Research Panel */}
      <ResearchPanel company={job.company} location={job.location} />

      {/* Notes */}
      <div className="mt-6 bg-white border border-gray-100 rounded-2xl shadow-sm p-5">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Your Notes</p>
        <textarea
          value={notes}
          onChange={e => setNotes(e.target.value)}
          rows={3}
          placeholder="Add notes about this role…"
          className="w-full border border-gray-200 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-transparent resize-none bg-gray-50"
        />
        <button
          onClick={() => updateM.mutate({ notes })}
          className="mt-2 text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-1.5 rounded-lg transition font-medium"
        >
          Save Notes
        </button>
      </div>

      {/* Actions */}
      <div className="mt-4 flex gap-3">
        <button
          onClick={() => updateM.mutate({ is_applied: !job.is_applied })}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition ${
            job.is_applied
              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          }`}
        >
          {job.is_applied ? <CheckCircle size={15} /> : <Circle size={15} />}
          {job.is_applied ? 'Applied' : 'Mark as Applied'}
        </button>
        <a
          href={job.application_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 bg-violet-600 text-white px-4 py-2.5 rounded-xl text-sm font-medium hover:bg-violet-700 transition"
        >
          <ExternalLink size={15} /> {applyButtonLabel(job.source)}
        </a>
      </div>
    </div>
  );
}
