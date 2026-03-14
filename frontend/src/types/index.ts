export interface Job {
  id:              number;
  job_title:       string;
  company:         string;
  location:        string;
  salary:          string;
  description:     string;
  posted_date:     string;
  application_url: string;
  scraped_at:      string;
  match_score:     number | null;
  matched_skills:  string[];
  missing_skills:  string[];
  is_applied:      boolean;
  applied_date:    string | null;
  notes:           string | null;
}

export interface JobsResponse {
  total:     number;
  page:      number;
  page_size: number;
  jobs:      Job[];
}

export interface Stats {
  total_jobs:    number;
  avg_score:     number;
  applied_count: number;
  high_match:    number;
}

export interface ScrapeSourceStatus {
  running:     boolean;
  last_result: Record<string, unknown>;
}

export interface ScrapeStatus {
  seek:       ScrapeSourceStatus;
  iworkforsa: ScrapeSourceStatus;
}

export interface ScrapeResponse {
  scraped: number;
  scored:  number;
  message: string;
}
