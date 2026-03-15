import axios from 'axios';
import type { Job, JobsResponse, Stats, ScrapeResponse, ScrapeStatus } from '../types';

const api = axios.create({ baseURL: '/api' });

export const fetchJobs = async (params: {
  min_score?:  number;
  location?:   string;
  is_applied?: boolean;
  search?:     string;
  sort_by?:    string;
  sort_order?: string;
  source?:     string;
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

export const deleteJobsBySource = async (source: string): Promise<{ deleted: number; source: string }> => {
  const { data } = await api.delete(`/jobs/source/${source}`);
  return data;
};

export const triggerSeekScrape = async (req: {
  keywords:  string[];
  location:  string;
  max_pages: number;
}): Promise<ScrapeResponse> => {
  const { data } = await api.post<ScrapeResponse>('/scrape/seek', req);
  return data;
};

export const triggerIworkforsaScrape = async (): Promise<ScrapeResponse> => {
  const { data } = await api.post<ScrapeResponse>('/scrape/iworkforsa');
  return data;
};

export const triggerIndeedScrape = async (req: {
  keywords:  string[];
  location:  string;
  max_pages: number;
}): Promise<ScrapeResponse> => {
  const { data } = await api.post<ScrapeResponse>('/scrape/indeed', req);
  return data;
};

export const fetchScrapeStatus = async (): Promise<ScrapeStatus> => {
  const { data } = await api.get<ScrapeStatus>('/scrape/status');
  return data;
};
