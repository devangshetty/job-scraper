import axios from 'axios';
import type { Job, JobsResponse, Stats, ScrapeRequest, ScrapeResponse } from '../types';

const api = axios.create({ baseURL: '/api' });

export const fetchJobs = async (params: {
  min_score?:  number;
  location?:   string;
  is_applied?: boolean;
  search?:     string;
  sort_by?:    string;
  sort_order?: string;
  page?:       number;
  page_size?:  number;
}): Promise<JobsResponse> => {
  const { data } = await api.get<JobsResponse>('/jobs', { params });
  return data;
};

export const fetchJob = async (id: number): Promise<Job> => {
  const { data } = await api.get<Job>(`/jobs/${id}`);
  return data;
};

export const updateJob = async (
  id: number,
  update: { is_applied?: boolean; notes?: string }
): Promise<Job> => {
  const { data } = await api.patch<Job>(`/jobs/${id}`, update);
  return data;
};

export const fetchStats = async (): Promise<Stats> => {
  const { data } = await api.get<Stats>('/jobs/stats');
  return data;
};

export const triggerScrape = async (req: ScrapeRequest): Promise<ScrapeResponse> => {
  const { data } = await api.post<ScrapeResponse>('/scrape', req);
  return data;
};

export const fetchScrapeStatus = async (): Promise<{ running: boolean; last_result?: Record<string, unknown> }> => {
  const { data } = await api.get('/scrape/status');
  return data;
};
