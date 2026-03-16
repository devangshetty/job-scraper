import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchJob, updateJob } from '../api/client';
import { ArrowLeft, ExternalLink, CheckCircle, Circle } from 'lucide-react';

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
        <div className="flex justify-between items-start mb-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-gray-800">{job.job_title}</h1>
              {job.source && (
                <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">
                  {sourceLabel}
                </span>
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
        <div className="mb-5">
          <p className="text-xs font-semibold text-gray-500 mb-1">Job Description</p>
          <div className="text-sm text-gray-700 whitespace-pre-wrap bg-gray-50 rounded p-3 max-h-80 overflow-y-auto leading-relaxed">
            {job.description || 'No description available.'}
          </div>
        </div>
        <div className="mb-5">
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
