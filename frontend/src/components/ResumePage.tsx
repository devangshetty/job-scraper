import { useRef, useState } from 'react'
import { uploadResume, summariseResume, fetchResumeStatus, fetchModelSettings, setModel } from '../api/client'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { UploadCloud, FileText, CheckCircle, AlertCircle, RefreshCw, ChevronDown, ChevronUp, Cpu } from 'lucide-react'

const MAX_MB = 3
const MAX_BYTES = MAX_MB * 1024 * 1024

function CollapsibleText({ text, label }: { text: string; label: string }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="bg-green-50 border border-green-200 rounded-lg overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-green-100 transition"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-2">
          <CheckCircle size={16} className="text-green-600 shrink-0" />
          <span className="text-sm font-medium text-green-700">
            {label} - click to {expanded ? 'collapse' : 'expand'}
          </span>
        </div>
        {expanded
          ? <ChevronUp size={16} className="text-green-600 shrink-0" />
          : <ChevronDown size={16} className="text-green-600 shrink-0" />
        }
      </button>
      {expanded && (
        <div className="px-4 pb-4 max-h-96 overflow-y-auto">
          <pre className="text-xs text-gray-600 whitespace-pre-wrap leading-relaxed font-mono">
            {text}
          </pre>
        </div>
      )}
    </div>
  )
}

function ModelSelector() {
  const qc = useQueryClient()
  const [saved, setSaved] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['modelSettings'],
    queryFn: fetchModelSettings,
    staleTime: 0,
  })

  const mutation = useMutation({
    mutationFn: (model_id: string) => setModel(model_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['modelSettings'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  if (isLoading || !data) return null

  return (
    <div className="p-4 bg-white border border-gray-200 rounded-lg shadow-sm">
      <div className="flex items-center gap-2 mb-3">
        <Cpu size={16} className="text-gray-500" />
        <span className="text-sm font-semibold text-gray-700">Groq Model (used for gap analysis)</span>
        {saved && (
          <span className="ml-auto text-xs text-green-600 flex items-center gap-1">
            <CheckCircle size={12} /> Saved
          </span>
        )}
      </div>
      <div className="flex flex-col gap-2">
        {data.available_models.map((m: { id: string; label: string; recommended: boolean }) => (
          <label
            key={m.id}
            className={`flex items-center gap-3 px-3 py-2 rounded-lg border cursor-pointer transition ${
              data.current_model === m.id
                ? 'border-indigo-400 bg-indigo-50'
                : 'border-gray-200 hover:bg-gray-50'
            }`}
          >
            <input
              type="radio"
              name="groq_model"
              value={m.id}
              checked={data.current_model === m.id}
              onChange={() => mutation.mutate(m.id)}
              className="accent-indigo-600"
            />
            <span className="text-sm text-gray-700">{m.label}</span>
            {m.recommended && (
              <span className="ml-auto text-xs bg-indigo-100 text-indigo-600 px-2 py-0.5 rounded-full font-medium">
                Recommended
              </span>
            )}
          </label>
        ))}
      </div>
      <p className="mt-3 text-xs text-gray-400">
        This setting is persisted locally. The resume summariser always uses the fast 8B model.
      </p>
    </div>
  )
}

export default function ResumePage() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)
  const [uploadedText, setUploadedText] = useState<string | null>(null)

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['resumeStatus'],
    queryFn: fetchResumeStatus,
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['resumeStatus'] })
    },
  })

  function validateAndUpload(file: File) {
    setLocalError(null)
    setUploadedText(null)
    if (file.type !== 'application/pdf') {
      setLocalError('Only PDF files are accepted.')
      return
    }
    if (file.size > MAX_BYTES) {
      setLocalError(`File is too large. Maximum size is ${MAX_MB} MB.`)
      return
    }
    uploadMutation.mutate(file)
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) validateAndUpload(file)
    e.target.value = ''
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) validateAndUpload(file)
  }

  const uploading      = uploadMutation.isPending
  const summarising    = summariseMutation.isPending
  const uploadError    = uploadMutation.error?.message ?? null
  const summariseError = summariseMutation.error?.message ?? null
  const rawTextToShow  = uploadedText ?? status?.raw_text ?? null

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-800 mb-1">Resume</h1>
      <p className="text-sm text-gray-500 mb-6">
        Upload your resume PDF. We extract the text, then use Groq to generate a structured summary
        that is stored locally and used for all gap analyses.
      </p>

      {/* Upload zone */}
      <div
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition ${
          dragOver
            ? 'border-blue-400 bg-blue-50'
            : 'border-gray-300 bg-white hover:border-blue-300 hover:bg-gray-50'
        }`}
        onClick={() => fileRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <UploadCloud className="mx-auto mb-3 text-gray-400" size={36} />
        <p className="text-sm font-medium text-gray-700">
          {uploading ? 'Uploading...' : 'Click or drag and drop your resume PDF'}
        </p>
        <p className="text-xs text-gray-400 mt-1">PDF only, max {MAX_MB} MB</p>
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={onFileChange}
        />
      </div>

      {(localError || uploadError) && (
        <div className="mt-3 flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          <AlertCircle size={16} className="mt-0.5 shrink-0" />
          {localError || uploadError}
        </div>
      )}

      {!statusLoading && rawTextToShow && (
        <div className="mt-4">
          <CollapsibleText text={rawTextToShow} label="Extracted text" />
        </div>
      )}

      {!statusLoading && status?.has_resume && (
        <div className="mt-6 flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <FileText size={16} className="text-gray-500" />
            <span className="text-sm font-semibold text-gray-700">
              Current resume: <span className="font-normal text-gray-500">{status.filename}</span>
            </span>
          </div>

          {!status.has_summary && (
            <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
              <p className="text-sm text-yellow-800 mb-3">
                No summary yet. Click below to send your resume to Groq and generate a structured profile.
                This is a one-time call and the result is stored locally.
              </p>
              <button
                onClick={() => summariseMutation.mutate()}
                disabled={summarising}
                className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2"
              >
                {summarising
                  ? <><RefreshCw size={14} className="animate-spin" /> Summarising...</>
                  : 'Generate Resume Summary'
                }
              </button>
              {summariseError && (
                <p className="mt-2 text-xs text-red-600">{summariseError}</p>
              )}
            </div>
          )}

          {status.has_summary && status.summary && (
            <div className="p-4 bg-white border border-gray-200 rounded-lg shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <CheckCircle size={16} className="text-green-500" />
                  <span className="text-sm font-semibold text-gray-700">Resume Summary (used for gap analysis)</span>
                </div>
                <button
                  onClick={() => summariseMutation.mutate()}
                  disabled={summarising}
                  className="text-xs text-gray-400 hover:text-indigo-600 flex items-center gap-1"
                >
                  <RefreshCw size={12} className={summarising ? 'animate-spin' : ''} />
                  Re-generate
                </button>
              </div>
              <pre className="text-xs text-gray-600 whitespace-pre-wrap leading-relaxed font-mono">
                {status.summary}
              </pre>
            </div>
          )}

          <ModelSelector />
        </div>
      )}
    </div>
  )
}
