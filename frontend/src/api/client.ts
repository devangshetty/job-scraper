import axios from 'axios'

const api = axios.create({
  baseURL: 'http://localhost:8000',
})

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

export const purgeDuplicates = () =>
  api.delete('/api/jobs/purge/duplicates').then((r) => r.data)

export const purgeNonIct = () =>
  api.delete('/api/jobs/purge/non-ict').then((r) => r.data)

// --- Scrape ---
export const scrapeSeek = (data: Record<string, unknown>) =>
  api.post('/api/scrape/seek', data).then((r) => r.data)

export const scrapeIndeed = (data: Record<string, unknown>) =>
  api.post('/api/scrape/indeed', data).then((r) => r.data)

export const scrapeIWorkForSA = () =>
  api.post('/api/scrape/iworkforsa').then((r) => r.data)

export const fetchScrapeStatus = () =>
  api.get('/api/scrape/status').then((r) => r.data)

// --- LLM ---
export const runGapAnalysis = (jobId: number) =>
  api.post(`/api/llm/gap-analysis/${jobId}`).then((r) => r.data)
