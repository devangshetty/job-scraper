import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchJob, updateJob, runGapAnalysis, fetchGapModelSettings, setGapModel, agentSearch } from '../api/client';
import { ArrowLeft, ExternalLink, CheckCircle, Circle, Zap, AlertTriangle, Info, Lightbulb, ChevronDown, Users, Loader } from 'lucide-react';

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

const VERDICT_STYLES: Record<string, string> = {
  'Strong Match':  'bg-green-100 text-green-700 border-green-300',
  'Good Match':    'bg-blue-100 text-blue-700 border-blue-300',
  'Partial Match': 'bg-yellow-100 text-yellow-700 border-yellow-300',
  'Weak Match':    'bg-red-100 text-red-600 border-red-300',
}

function GapAnalysisPanel({ jobId }: { jobId: number }) {
  const qc = useQueryClient()
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [selectedModel, setSelectedModel] = useState<string | null>(null)

  const { data: modelData } = useQuery({
    queryKey: ['gapModel'],
    queryFn:  fetchGapModelSettings,
    staleTime: 30_000,
  })

  const activeModel = selectedModel ?? modelData?.current_model ?? 'llama-3.1-8b-instant'

  const mutation = useMutation({
    mutationFn: async () => {
      // persist the chosen model then run analysis
      if (selectedModel && selectedModel !== modelData?.current_model) {
        await setGapModel(selectedModel)
        qc.invalidateQueries({ queryKey: ['gapModel'] })
      }
      return runGapAnalysis(jobId)
    },
    onSuccess: (data) => setResult(data),
  })

  const running = mutation.isPending
  const error   = mutation.error?.message ?? null

  const verdictStyle = result
    ? (VERDICT_STYLES[(result.match_verdict as string)] ?? 'bg-gray-100 text-gray-600 border-gray-300')
    : ''

  return (
    <div className="mt-6 border border-gray-200 rounded-xl overflow-hidden">
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <Zap size={15} className="text-indigo-500" />
          <span className="text-sm font-semibold text-gray-700">AI Gap Analysis</span>
          {result && (
            <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${verdictStyle}`}>
              {result.match_verdict as string}
            </span>
          )}
        </div>

        {/* Model dropdown */}
        {modelData && (
          <div className="flex items-center gap-2">
            <div className="relative">
              <select
                value={activeModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 pr-6 bg-white text-gray-600 appearance-none cursor-pointer hover:border-gray-300 focus:outline-none focus:ring-1 focus:ring-indigo-400"
              >
                {modelData.available_models.map((m: { id: string; label: string }) => (
                  <option key={m.id} value={m.id}>{m.label}</option>
                ))}
              </select>
              <ChevronDown size={12} className="absolute right-1.5 top-2 text-gray-400 pointer-events-none" />
            </div>
            <button
              onClick={() => mutation.mutate()}
              disabled={running}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white text-xs font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition"
            >
              {running ? 'Analysing...' : result ? 'Re-run' : 'Run Analysis'}
            </button>
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="px-4 py-3 bg-red-50 text-sm text-red-600 border-b border-red-200">
          {error}
        </div>
      )}

      {/* Loading state */}
      {running && (
        <div className="px-4 py-6 text-center text-sm text-gray-400">
          Calling Groq API - usually takes 2-5 seconds...
        </div>
      )}

      {/* Results */}
      {result && !running && (
        <div className="p-4 flex flex-col gap-4">

          {/* Summary */}
          <p className="text-sm text-gray-700 leading-relaxed">{result.summary as string}</p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* You have */}
            <div>
              <p className="text-xs font-semibold text-green-700 flex items-center gap-1 mb-1.5">
                <CheckCircle size={12} /> You have
              </p>
              <div className="flex flex-wrap gap-1">
                {(result.you_have as string[]).map(s => (
                  <span key={s} className="text-xs bg-green-50 text-green-700 border border-green-200 px-2 py-0.5 rounded">{s}</span>
                ))}
              </div>
            </div>

            {/* Missing */}
            <div>
              <p className="text-xs font-semibold text-red-600 flex items-center gap-1 mb-1.5">
                <AlertTriangle size={12} /> You are missing
              </p>
              <div className="flex flex-wrap gap-1">
                {(result.you_are_missing as string[]).map(s => (
                  <span key={s} className="text-xs bg-red-50 text-red-600 border border-red-200 px-2 py-0.5 rounded">{s}</span>
                ))}
                {(result.you_are_missing as string[]).length === 0 && (
                  <span className="text-xs text-gray-400">Nothing significant</span>
                )}
              </div>
            </div>
          </div>

          {/* You can claim */}
          {(result.you_can_claim as string[]).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-blue-600 flex items-center gap-1 mb-1.5">
                <Lightbulb size={12} /> Highlight in cover letter
              </p>
              <div className="flex flex-wrap gap-1">
                {(result.you_can_claim as string[]).map(s => (
                  <span key={s} className="text-xs bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded">{s}</span>
                ))}
              </div>
            </div>
          )}

          {/* Red flags */}
          {(result.red_flags as string[]).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-orange-600 flex items-center gap-1 mb-1.5">
                <Info size={12} /> Red flags
              </p>
              <ul className="list-disc list-inside">
                {(result.red_flags as string[]).map(s => (
                  <li key={s} className="text-xs text-orange-700">{s}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!result && !running && !error && (
        <div className="px-4 py-6 text-center text-sm text-gray-400">
          Select a model and click Run Analysis to get an AI-powered gap analysis for this job.
        </div>
      )}
    </div>
  )
}

interface SearchResult {
  title:   string;
  url:     string;
  snippet: string;
}

function parseContact(result: SearchResult): { name: string; role: string } {
  // Bing titles come as "Name - Role at Company | LinkedIn"
  const withoutLinkedIn = result.title.replace(/\s*\|\s*LinkedIn.*$/i, '').trim();
  const dashIdx = withoutLinkedIn.indexOf(' - ');
  if (dashIdx !== -1) {
    return {
      name: withoutLinkedIn.slice(0, dashIdx).trim(),
      role: withoutLinkedIn.slice(dashIdx + 3).trim(),
    };
  }
  return { name: withoutLinkedIn, role: '' };
}

function ResearchPanel({ company }: { company: string; location?: string | null }) {
  const [results, setResults]   = useState<SearchResult[]>([]);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [hasRun, setHasRun]     = useState(false);

  async function handleSearch() {
    setLoading(true);
    setError(null);
    try {
      const data = await agentSearch(`"${company}" linkedin.com/in`, 10);
      const profiles = (data.results as SearchResult[]).filter(r =>
        r.url.includes('linkedin.com/in/')
      );
      setResults(profiles);
      setHasRun(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Search failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mt-6 border border-gray-200 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <Users size={15} className="text-blue-500" />
          <span className="text-sm font-semibold text-gray-700">Find People at {company}</span>
        </div>
        <button
          onClick={handleSearch}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition"
        >
          {loading ? <Loader size={13} className="animate-spin" /> : <Users size={13} />}
          {loading ? 'Searching...' : hasRun ? 'Search Again' : 'Find People'}
        </button>
      </div>

      {loading && (
        <div className="px-4 py-6 text-center text-sm text-gray-400">
          <Loader size={16} className="animate-spin inline mr-2" />
          Searching for LinkedIn profiles at {company}...
        </div>
      )}

      {error && !loading && (
        <div className="px-4 py-3 text-sm text-red-600 bg-red-50">{error}</div>
      )}

      {!loading && hasRun && results.length === 0 && (
        <div className="px-4 py-6 text-center text-sm text-gray-400">
          No results found for this company. Try a different search.
        </div>
      )}

      {!loading && results.length > 0 && (
        <div className="divide-y divide-gray-100">
          {results.map((r, i) => {
            const { name, role } = parseContact(r);
            return (
              <div key={i} className="flex items-start justify-between px-4 py-3 gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-800">{name}</p>
                  {role && <p className="text-xs text-gray-500 mt-0.5">{role}</p>}
                  {r.snippet && (
                    <p className="text-xs text-gray-400 mt-1 line-clamp-2">{r.snippet}</p>
                  )}
                </div>
                <a
                  href={r.url}
                  target="_blank"
                  rel="noopener noreferrer"
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
        <div className="px-4 py-5 text-center text-sm text-gray-400">
          Click Find People to search for LinkedIn profiles at {company}.
        </div>
      )}
    </div>
  );
}

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

  if (isLoading) return <div className="p-8 text-gray-400 text-center">Loading...</div>;
  if (!job)      return <div className="p-8 text-red-500">Job not found.</div>;

  const matchedSkills = parseSkills(job.matched_skills);
  const missingSkills = parseSkills(job.missing_skills);
  const isIndeed      = job.source === 'indeed';
  const hasDescription = !!job.description && job.description.length > 80;

  const scoreColor = !job.match_score ? 'text-gray-400' :
                     job.match_score >= 0.7 ? 'text-green-600' :
                     job.match_score >= 0.5 ? 'text-yellow-600' : 'text-red-600';

  const sourceLabel =
    job.source === 'iworkforsa' ? 'iWorkForSA' :
    job.source === 'indeed'     ? 'Indeed' :
    job.source === 'seek'       ? 'Seek' : job.source ?? '';

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <button onClick={() => navigate(-1)}
        className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 mb-4">
        <ArrowLeft size={14} /> Back
      </button>

      <div className="bg-white rounded-xl border p-6">
        {/* Header */}
        <div className="flex justify-between items-start mb-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-gray-800">{job.job_title}</h1>
              {job.source && (
                <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">{sourceLabel}</span>
              )}
            </div>
            <p className="text-gray-500">{job.company} &middot; {job.location}</p>
            {job.salary      && <p className="text-sm text-gray-500 mt-0.5">{job.salary}</p>}
            {job.posted_date && <p className="text-xs text-gray-400 mt-0.5">Posted: {job.posted_date}</p>}
          </div>
          {job.match_score !== null && (
            <div className="text-right">
              <p className={`text-3xl font-bold ${scoreColor}`}>{Math.round((job.match_score ?? 0) * 100)}%</p>
              <p className="text-xs text-gray-400">match score</p>
            </div>
          )}
        </div>

        {isIndeed && (
          <div className="mb-5 p-3 bg-blue-50 border border-blue-200 rounded-lg">
            <p className="text-sm text-blue-700">
              Indeed limits automated access to full job descriptions. Match score and skills are based on the short snippet only.
              Click <strong>Apply on Indeed</strong> below to view the full listing.
            </p>
          </div>
        )}

        {!isIndeed && (
          hasDescription ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
              <div>
                <p className="text-xs font-semibold text-green-700 mb-1">Matched Skills</p>
                <div className="flex flex-wrap gap-1">
                  {matchedSkills.length > 0
                    ? matchedSkills.map(s => (
                        <span key={s} className="text-xs bg-green-50 text-green-700 border border-green-200 px-2 py-0.5 rounded">{s}</span>
                      ))
                    : <span className="text-xs text-gray-400">None detected</span>
                  }
                </div>
              </div>
              <div>
                <p className="text-xs font-semibold text-red-600 mb-1">Missing Skills</p>
                <div className="flex flex-wrap gap-1">
                  {missingSkills.slice(0, 10).map(s => (
                    <span key={s} className="text-xs bg-red-50 text-red-600 border border-red-200 px-2 py-0.5 rounded">{s}</span>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="mb-5 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
              <p className="text-sm text-yellow-700">
                No description was scraped for this job. Skills and match score may not be accurate.
              </p>
            </div>
          )
        )}

        <div className="mb-5">
          <p className="text-xs font-semibold text-gray-500 mb-1">
            {isIndeed ? 'Snippet' : 'Job Description'}
          </p>
          <div className="text-sm text-gray-700 whitespace-pre-wrap bg-gray-50 rounded p-3 max-h-80 overflow-y-auto leading-relaxed">
            {job.description || 'No description available.'}
          </div>
        </div>

        {/* Gap Analysis Panel - skip for Indeed (no full JD) */}
        {!isIndeed && hasDescription && (
          <GapAnalysisPanel jobId={jobId} />
        )}

        {/* Research Panel - find people at this company on LinkedIn */}
        <ResearchPanel company={job.company} location={job.location} />

        <div className="mt-6 mb-5">
          <p className="text-xs font-semibold text-gray-500 mb-1">Your Notes</p>
          <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={3}
            placeholder="Add notes about this role..."
            className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none" />
          <button onClick={() => updateM.mutate({ notes })}
            className="mt-1 text-xs bg-gray-100 hover:bg-gray-200 px-3 py-1.5 rounded transition">
            Save Notes
          </button>
        </div>

        <div className="flex gap-3">
          <button onClick={() => updateM.mutate({ is_applied: !job.is_applied })}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition ${
              job.is_applied
                ? 'bg-green-100 text-green-700 hover:bg-green-200'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}>
            {job.is_applied ? <CheckCircle size={15} /> : <Circle size={15} />}
            {job.is_applied ? 'Applied' : 'Mark as Applied'}
          </button>
          <a href={job.application_url} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition">
            <ExternalLink size={15} /> {applyButtonLabel(job.source)}
          </a>
        </div>
      </div>
    </div>
  );
}
