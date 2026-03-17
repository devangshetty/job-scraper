import axios from 'axios'

const api = axios.create({
  baseURL: 'http://localhost:8000',
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    const detail = err?.response?.data?.detail
    if (detail) err.message = typeof detail === 'string' ? detail : JSON.stringify(detail)
    return Promise.reject(err)
  }
)

// --- Jobs ---
export const fetchJobs = (params: Record<string, unknown>) =>
  api.get('/api/jobs', { params }).then((r) => r.data)

export const fetchJob = (id: number) =>
  api.get(`/api/jobs/${id}`).then((r) => r.data)

export const fetchStats = () =>
  api.get('/api/jobs/stats').then((r) => r.data)

export const updateJob = (id: number, data: Record<string, unknown>) =>
  api.patch(`/api/jobs/${id}`, data).then((r) => r.data)

export const rescoreSource = (source: string) =>
  api.post(`/api/jobs/rescore/${source}`).then((r) => r.data)

export const deleteSource = (source: string) =>
  api.delete(`/api/jobs/source/${source}`).then((r) => r.data)

export const rescoreJobsBySource  = rescoreSource
export const deleteJobsBySource   = deleteSource

export const purgeDuplicates = () =>
  api.delete('/api/jobs/purge/duplicates').then((r) => r.data)

export const purgeNonIct = () =>
  api.delete('/api/jobs/purge/non-ict').then((r) => r.data)

export const fetchJobCountBySource = (source: string) =>
  api.get('/api/jobs', { params: { source, page: 1, page_size: 1 } })
    .then((r) => r.data.total as number)

// --- Scrape ---
export const scrapeSeek = (data: Record<string, unknown>) =>
  api.post('/api/scrape/seek', data).then((r) => r.data)

export const scrapeIndeed = (data: Record<string, unknown>) =>
  api.post('/api/scrape/indeed', data).then((r) => r.data)

export const scrapeIWorkForSA = () =>
  api.post('/api/scrape/iworkforsa').then((r) => r.data)

export const fetchScrapeStatus = () =>
  api.get('/api/scrape/status').then((r) => r.data)

export const triggerSeekScrape       = scrapeSeek
export const triggerIndeedScrape     = scrapeIndeed
export const triggerIworkforsaScrape = scrapeIWorkForSA

// --- Resume ---
export const uploadResume = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/api/resume/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then((r) => r.data)
}

export const summariseResume = () =>
  api.post('/api/resume/summarise').then((r) => r.data)

export const fetchResumeStatus = () =>
  api.get('/api/resume/status').then((r) => r.data)

// --- Settings ---
export const fetchModelSettings = () =>
  api.get('/api/settings/model').then((r) => r.data)

export const setModel = (model_id: string) =>
  api.post('/api/settings/model', { model_id }).then((r) => r.data)

// --- LLM ---
export const runGapAnalysis = (jobId: number) =>
  api.post(`/api/llm/gap-analysis/${jobId}`).then((r) => r.data)
