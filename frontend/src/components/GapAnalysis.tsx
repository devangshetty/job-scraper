import { useState } from 'react'
import { runGapAnalysis } from '../api/client'

interface GapAnalysisResult {
  you_have: string[]
  you_are_missing: string[]
  you_can_claim: string[]
  summary: string
  red_flags: string[]
  match_verdict: 'Strong Match' | 'Good Match' | 'Partial Match' | 'Weak Match'
}

const verdictColors: Record<string, string> = {
  'Strong Match': 'bg-green-100 text-green-800 border-green-300',
  'Good Match': 'bg-blue-100 text-blue-800 border-blue-300',
  'Partial Match': 'bg-yellow-100 text-yellow-800 border-yellow-300',
  'Weak Match': 'bg-red-100 text-red-800 border-red-300',
}

function TagList({ items, color }: { items: string[]; color: string }) {
  if (!items.length) return <p className="text-sm text-gray-400 italic">None identified</p>
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <span key={item} className={`text-xs px-2 py-1 rounded-full border font-medium ${color}`}>
          {item}
        </span>
      ))}
    </div>
  )
}

export default function GapAnalysis({ jobId, isIndeed }: { jobId: number; isIndeed: boolean }) {
  const [result, setResult] = useState<GapAnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleRun = async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await runGapAnalysis(jobId)
      setResult(data)
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : 'Gap analysis failed. Check your GROQ_API_KEY is set in .env'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  if (isIndeed) {
    return (
      <div className="mt-6 p-4 bg-gray-50 border border-gray-200 rounded-lg">
        <p className="text-sm text-gray-500">
          Gap analysis is not available for Indeed jobs as only a short snippet is stored, not the full description.
          Click <strong>Apply on Indeed</strong> to view the full job posting.
        </p>
      </div>
    )
  }

  return (
    <div className="mt-6">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold text-gray-800">LLM Gap Analysis</h3>
        {!result && (
          <button
            onClick={handleRun}
            disabled={loading}
            className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {loading ? (
              <>
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                Analysing...
              </>
            ) : (
              'Run Gap Analysis'
            )}
          </button>
        )}
        {result && (
          <button
            onClick={() => setResult(null)}
            className="text-xs text-gray-400 hover:text-gray-600 underline"
          >
            Re-run
          </button>
        )}
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {!result && !loading && !error && (
        <p className="text-sm text-gray-400">
          Uses Groq (free tier) to analyse this job against your resume skills and identify gaps.
        </p>
      )}

      {result && (
        <div className="space-y-5">
          {/* Verdict badge */}
          <div>
            <span
              className={`inline-block text-sm font-semibold px-3 py-1 rounded-full border ${
                verdictColors[result.match_verdict] ?? 'bg-gray-100 text-gray-700 border-gray-300'
              }`}
            >
              {result.match_verdict}
            </span>
          </div>

          {/* Summary */}
          <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
            <p className="text-sm text-gray-700 leading-relaxed">{result.summary}</p>
          </div>

          {/* Skills grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
              <h4 className="text-xs font-bold text-green-700 uppercase tracking-wide mb-2">You Have</h4>
              <TagList items={result.you_have} color="bg-green-100 text-green-800 border-green-200" />
            </div>

            <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
              <h4 className="text-xs font-bold text-red-700 uppercase tracking-wide mb-2">You Are Missing</h4>
              <TagList items={result.you_are_missing} color="bg-red-100 text-red-800 border-red-200" />
            </div>

            <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <h4 className="text-xs font-bold text-blue-700 uppercase tracking-wide mb-2">Worth Claiming</h4>
              <TagList items={result.you_can_claim} color="bg-blue-100 text-blue-800 border-blue-200" />
            </div>
          </div>

          {/* Red flags */}
          {result.red_flags.length > 0 && (
            <div className="p-4 bg-orange-50 border border-orange-200 rounded-lg">
              <h4 className="text-xs font-bold text-orange-700 uppercase tracking-wide mb-2">Red Flags</h4>
              <TagList items={result.red_flags} color="bg-orange-100 text-orange-800 border-orange-200" />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
