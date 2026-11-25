import type { JobFields } from './types';

const dateFormat = new Intl.DateTimeFormat('en-IN', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
});
const dateTimeFormat = new Intl.DateTimeFormat('en-IN', {
  day: 'numeric',
  month: 'short',
  hour: 'numeric',
  minute: '2-digit',
});

export function formatDate(value: string | null | undefined): string {
  if (!value) return 'Not stated';
  return dateFormat.format(new Date(value.length === 10 ? `${value}T00:00:00` : value));
}

export function formatDateTime(value: string): string {
  return dateTimeFormat.format(new Date(value));
}

export function daysUntil(deadline: string | null, now = new Date()): number | null {
  if (!deadline) return null;
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((new Date(`${deadline}T00:00:00`).getTime() - start.getTime()) / 86_400_000);
}

export function deadlineText(deadline: string | null, now?: Date): string {
  const days = daysUntil(deadline, now);
  if (days === null) return 'No deadline stated';
  if (days < 0) return 'Closed';
  if (days === 0) return 'Closes today';
  if (days === 1) return 'Closes tomorrow';
  if (days <= 14) return `Closes in ${days} days`;
  return `Closes ${formatDate(deadline)}`;
}

function rupees(value: number, yearly: boolean): string {
  if (yearly && value >= 100_000) return `₹${+(value / 100_000).toFixed(1)} lakh`;
  return `₹${value.toLocaleString('en-IN')}`;
}

export function payText(
  job: Pick<JobFields, 'stipend_min' | 'stipend_max' | 'job_type'>,
): string | null {
  const { stipend_min: low, stipend_max: high } = job;
  if (low === null && high === null) return null;
  const yearly = job.job_type === 'full-time';
  const unit = yearly ? 'a year' : 'a month';
  if (low !== null && high !== null && low !== high)
    return `${rupees(low, yearly)} to ${rupees(high, yearly)} ${unit}`;
  return `${rupees((high ?? low)!, yearly)} ${unit}`;
}

export function placeText(job: Pick<JobFields, 'location' | 'remote'>): string {
  if (job.remote && job.location) return `${job.location} or remote`;
  if (job.remote) return 'Remote';
  return job.location || 'Location not stated';
}

export function typeText(type: JobFields['job_type']): string {
  return type === 'internship' ? 'Internship' : 'Full-time';
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count.toLocaleString('en-IN')} ${count === 1 ? one : many}`;
}
