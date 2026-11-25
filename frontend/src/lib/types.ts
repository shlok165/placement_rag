export type JobStatus = 'draft' | 'pending' | 'indexed' | 'failed' | 'expired' | 'archived';
export type JobType = 'internship' | 'full-time';

export type JobFields = {
  company: string;
  title: string;
  description: string;
  requirements: string;
  skills: string[];
  location: string;
  remote: boolean;
  job_type: JobType;
  stipend_min: number | null;
  stipend_max: number | null;
  duration_months: number | null;
  deadline: string | null;
  apply_url: string;
};

export type Job = JobFields & { id: number; status: JobStatus; published_at: string | null };

export type Duplicate = {
  id: number;
  company: string;
  title: string;
  deadline: string | null;
  status: JobStatus;
  similarity: number;
};

export type Confidence = 'high' | 'medium' | 'low';

export type AdminJob = Job & {
  source: string;
  raw_text: string | null;
  parse_meta: {
    confidence?: Record<string, Confidence>;
    low_confidence?: string[];
    parsed_by?: 'live' | 'cache' | 'mock';
    needs_review?: boolean;
  };
  auto_publish: boolean;
  last_error: string | null;
  duplicate_of_id: number | null;
  created_at: string;
  updated_at: string;
  indexed: boolean;
  file_name: string | null;
  duplicates: Duplicate[];
};

export type AdminJobRow = {
  id: number;
  company: string;
  title: string;
  location: string;
  job_type: JobType;
  deadline: string | null;
  status: JobStatus;
  source: string;
  last_error: string | null;
  duplicate_of_id: number | null;
  needs_review: boolean;
  updated_at: string;
};

export type Page<T> = { items: T[]; total: number; page: number; page_size: number };
