import type { Stage } from './stages';

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

export type ScoreComponent = {
  key: string;
  label: string;
  value: number | null;
  weight: number;
  contribution: number;
  note: string;
};

export type Breakdown = {
  score: number;
  match_percent: number | null;
  components: ScoreComponent[];
  matched_skills: string[];
  missing_skills: string[];
  preference_checks: { key: string; label: string; met: boolean }[];
};

export type SearchHit = {
  job: Job;
  score: number;
  breakdown: Breakdown | null;
  saved: boolean;
  application_status: string | null;
};

export type SearchFilters = {
  job_type?: JobType | null;
  locations?: string[];
  remote?: boolean | null;
  min_stipend?: number | null;
  closing_within_days?: number | null;
};

/** Filters read from typed words by POST /search/parse, shown as chips before use. */
export type ParsedQuery = {
  query: string;
  filters: SearchFilters;
  chips: { key: keyof SearchFilters; label: string; value: string }[];
};

export type SearchResult = Page<SearchHit> & { personalized: boolean; weak_match: boolean };

export type Application = {
  id: number;
  status: Stage;
  notes: string;
  updated_at: string;
  job: Job;
};

export type JobDetail = {
  job: Job;
  breakdown: Breakdown | null;
  saved: boolean;
  application: Application | null;
  similar: Job[];
  /** The student's "more like this" (up) or "fewer like this" (down). */
  reaction: 'up' | 'down' | null;
};

export type Home = {
  recommended: SearchHit[];
  closing_soon: SearchHit[];
  pipeline: Record<string, number>;
  unread: number;
  profile_ready: boolean;
};

export type ParsedProfile = {
  education: { degree: string; institution: string; year: string }[];
  skills: string[];
  projects: { title: string; summary: string }[];
  experience: { role: string; organisation: string; summary: string }[];
};

export type Preferences = {
  roles: string[];
  locations: string[];
  remote_ok: boolean;
  job_types: JobType[];
  duration: number | null;
  start_window: string;
  min_stipend: number | null;
};

export type Profile = {
  skills: string[];
  parsed_profile: ParsedProfile;
  preferences: Preferences;
  resume_name: string | null;
  resume_text_redacted: string | null;
  updated_at: string | null;
};

export type ResumeResult = Profile & {
  redactions: Record<string, number>;
  parsed_by: 'live' | 'cache' | 'mock' | 'local';
};

export type AppNotification = {
  id: number;
  type: string;
  payload: { job_id?: number; title?: string; company?: string; deadline?: string | null };
  read_at: string | null;
  created_at: string;
};

export type SavedSearch = { id: number; name: string; query: string; filters: SearchFilters };

export type Citation = { job_id: number; title: string; company: string };

export type PendingAction = {
  id: number;
  kind: 'save_job' | 'track_application' | 'update_preferences' | 'remember';
  label: string;
  payload: Record<string, unknown>;
  status: 'pending' | 'confirmed' | 'rejected';
};

export type ChatMessage = {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  citations: Citation[];
  suggested_followups: string[];
  pending_actions: PendingAction[];
  notice: string | null;
  stopped: boolean;
  feedback: 'up' | 'down' | null;
  /** A checked outreach draft. It is shown to edit and copy, never sent. */
  draft?: Draft | null;
  created_at: string;
};

export type Draft = {
  job_id: number;
  kind: 'recruiter_note' | 'resume_focus';
  text: string;
};

export type ChatSession = { id: number; title: string; updated_at: string };

export type ChatStatus = {
  mode: 'mock' | 'live';
  consent: boolean;
  quota: { limit: number; used: number; remaining: number };
};

export type MemoryFact = { id: number; kind: string; text: string; created_at: string };
