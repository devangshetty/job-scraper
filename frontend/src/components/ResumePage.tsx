import { useRef, useState } from 'react'
import {
  uploadResume, summariseResume, fetchResumeStatus,
  fetchSummariserModelSettings, setSummariserModel,
} from '../api/client'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  UploadCloud, FileText, CheckCircle, AlertCircle,
  RefreshCw, ChevronDown, ChevronUp, Cpu,
} from 'lucide-react'

const MAX_MB    = 3
const MAX_BYTES = MAX_MB * 1024 * 1024

function CollapsibleText({ text, label }: { text: string; label: string }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="bg-white border border-gray-100 rounded-2xl overflow-hidden shadow-sm">
      <button
        className="w-full flex items-center justify-between px-5 py-3.5 hover:bg-gray-50 transition"
        onClick={() => setExpanded(v => !v)}
      >
        <div className="flex items-center gap-2">
          <CheckCircle size={14} className="text-emerald-500 shrink-0" />
          <span className="text-sm font-medium text-gray-700">
            {label} — click to {expanded ? 'collapse' : 'expand'}
          </span>
        </div>
        {expanded
          ? <ChevronUp size={15} className="text-gray-400 shrink-0" />
          : <ChevronDown size={15} className="text-gray-400 shrink-0" />}
      </button>
      {expanded && (
        <div className="px-5 pb-5 border-t border-gray-50 max-h-96 overflow-y-auto">
          <pre className="text-xs text-gray-500 whitespace-pre-wrap leading-relaxed font-mono mt-3">
            {text}
          </pre>
        </div>
      )}
    </div>
  )
}

function SummariserModelSelector() {
  const qc = useQueryClient()
  const [saved, setSaved] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['summariserModel'],
    queryFn: fetchSummariserModelSettings,
    staleTime: 0,
  })

  const mutation = useMutation({
    mutationFn: (model_id: string) => setSummariserModel(model_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['summariserModel'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  if (isLoading || !data) return null

  return (
    <div className="bg-white border border-gray-100 rounded-2xl shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-50">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 bg-gray-50 rounded-lg flex items-center justify-center">
            <Cpu size={13} className="text-gray-500" />
          </div>
          <span className="text-sm font-semibold text-gray-800">Summariser Model</span>
        </div>
        {saved && (
          <span className="text-xs text-emerald-600 flex items-center gap-1 font-medium">
            <CheckCircle size={12} /> Saved
          </span>
        )}
      </div>
      <div className="p-5 flex flex-col gap-2">
        {data.available_models.map((m: { id: string; label: string; recommended: boolean }) => (
          <label
            key={m.id}
            className={`flex items-center gap-3 px-4 py-3 rounded-xl border cursor-pointer transition ${
              data.current_model === m.id
                ? 'border-violet-300 bg-violet-50'
                : 'border-gray-200 hover:bg-gray-50'
            }`}
          >
            <input
              type="radio"
              name="summariser_model"
              value={m.id}
              checked={data.current_model === m.id}
              onChange={() => mutation.mutate(m.id)}
              className="accent-violet-600"
            />
            <span className="text-sm text-gray-700">{m.label}</span>
            {m.recommended && (
              <span className="ml-auto text-xs bg-violet-100 text-violet-600 px-2 py-0.5 rounded-full font-medium">
                Recommended
              </span>
            )}
          </label>
        ))}
        <p className="text-xs text-gray-400 mt-1">
          Used when you click Generate Resume Summary. Only runs once unless you re-generate.
        </p>
      </div>
    </div>
  )
}

export default function ResumePage() {
  const qc      = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [dragOver,     setDragOver]     = useState(false)
  const [localError,   setLocalError]   = useState<string | null>(null)
  const [uploadedText, setUploadedText] = useState<string | null>(null)

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['resumeStatus'],
    queryFn:  fetchResumeStatus,
    staleTime: 0,
  })

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadResume(file),
    onSuccess: (data) => {
      setUploadedText(data.raw_text)
      qc.invalidateQueries({ queryKey: ['resumeStatus'] })
    },
  })

  const summariseMutation = useMutation({
    mutationFn: summariseResume,
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['resumeStatus'] }),
  })

  function validateAndUpload(file: File) {
    setLocalError(null)
    setUploadedText(null)
    if (file.type !== 'application/pdf') { setLocalError('Only PDF files are accepted.'); return }
    if (file.size > MAX_BYTES)           { setLocalError(`File too large — max ${MAX_MB} MB.`); return }
    uploadMutation.mutate(file)
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]; if (f) validateAndUpload(f); e.target.value = ''
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault(); setDragOver(false)
    const f = e.dataTransfer.files?.[0]; if (f) validateAndUpload(f)
  }

  const uploading      = uploadMutation.isPending
  const summarising    = summariseMutation.isPending
  const uploadError    = uploadMutation.error?.message    ?? null
  const summariseError = summariseMutation.error?.message ?? null
  const rawTextToShow  = uploadedText ?? status?.raw_text ?? null

  return (
    <div className="p-8 max-w-2xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Resume</h1>
        <p className="text-sm text-gray-400 mt-1">
          Upload your PDF — we extract the text and use Groq to build a structured profile for gap analysis.
        </p>
      </div>

      {/* Upload zone */}
      <div
        className={`border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all ${
          dragOver
            ? 'border-violet-400 bg-violet-50'
            : 'border-gray-200 bg-white hover:border-violet-300 hover:bg-gray-50'
        }`}
        onClick={() => fileRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <div className="w-12 h-12 bg-gray-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
          <UploadCloud size={22} className="text-gray-400" />
        </div>
        <p className="text-sm font-semibold text-gray-700">
          {uploading ? 'Uploading…' : 'Click or drag & drop your resume'}
        </p>
        <p className="text-xs text-gray-400 mt-1">PDF only · max {MAX_MB} MB</p>
        <input ref={fileRef} type="file" accept="application/pdf" className="hidden" onChange={onFileChange} />
      </div>

      {/* Error */}
      {(localError || uploadError) && (
        <div className="mt-3 flex items-start gap-2 p-4 bg-red-50 border border-red-100 rounded-xl text-sm text-red-700">
          <AlertCircle size={15} className="mt-0.5 shrink-0" />
          {localError || uploadError}
        </div>
      )}

      {/* Extracted text */}
      {!statusLoading && rawTextToShow && (
        <div className="mt-4">
          <CollapsibleText text={rawTextToShow} label="Extracted text" />
        </div>
      )}

      {/* Resume actions */}
      {!statusLoading && status?.has_resume && (
        <div className="mt-6 flex flex-col gap-4">
          <div className="flex items-center gap-2 px-1">
            <FileText size={14} className="text-gray-400 shrink-0" />
            <span className="text-sm text-gray-600">
              <span className="font-medium text-gray-800">{status.filename}</span> uploaded
            </span>
          </div>

          {!status.has_summary && (
            <div className="p-5 bg-amber-50 border border-amber-100 rounded-2xl">
              <p className="text-sm text-amber-800 mb-4 leading-relaxed">
                No summary yet. Generate a structured profile via Groq — stored locally and reused for every gap analysis.
              </p>
              <button
                onClick={() => summariseMutation.mutate()}
                disabled={summarising}
                className="px-4 py-2.5 bg-violet-600 text-white text-sm font-medium rounded-xl hover:bg-violet-700 disabled:opacity-50 flex items-center gap-2 transition"
              >
                {summarising
                  ? <><RefreshCw size={14} className="animate-spin" /> Summarising…</>
                  : 'Generate Resume Summary'
                }
              </button>
              {summariseError && <p className="mt-2 text-xs text-red-600">{summariseError}</p>}
            </div>
          )}

          {status.has_summary && status.summary && (
            <div className="bg-white border border-gray-100 rounded-2xl shadow-sm overflow-hidden">
              <div className="flex items-center justify-between px-5 py-4 border-b border-gray-50">
                <div className="flex items-center gap-2">
                  <CheckCircle size={14} className="text-emerald-500" />
                  <span className="text-sm font-semibold text-gray-800">Resume Summary</span>
                  <span className="text-xs text-gray-400">used for gap analysis</span>
                </div>
                <button
                  onClick={() => summariseMutation.mutate()}
                  disabled={summarising}
                  className="text-xs text-gray-400 hover:text-violet-600 flex items-center gap-1.5 transition font-medium"
                >
                  <RefreshCw size={12} className={summarising ? 'animate-spin' : ''} />
                  Re-generate
                </button>
              </div>
              <div className="px-5 py-4 max-h-64 overflow-y-auto">
                <pre className="text-xs text-gray-500 whitespace-pre-wrap leading-relaxed font-mono">
                  {status.summary}
                </pre>
              </div>
            </div>
          )}

          <SummariserModelSelector />
        </div>
      )}
    </div>
  )
}
