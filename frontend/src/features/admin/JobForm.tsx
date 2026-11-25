import { useQuery } from '@tanstack/react-query';
import { TagInput } from '@/components/TagInput';
import { Badge } from '@/components/ui/display';
import { CheckRow, Field, Input, Select, Textarea } from '@/components/ui/form';
import { api, type ApiError } from '@/lib/api';
import type { Confidence, Duplicate, JobFields } from '@/lib/types';

export const emptyJob: JobFields = {
  company: '',
  title: '',
  description: '',
  requirements: '',
  skills: [],
  location: '',
  remote: false,
  job_type: 'internship',
  stipend_min: null,
  stipend_max: null,
  duration_months: null,
  deadline: null,
  apply_url: '',
};

export function pickFields(job: JobFields): JobFields {
  return Object.fromEntries(
    Object.keys(emptyJob).map((key) => [key, job[key as keyof JobFields]]),
  ) as JobFields;
}

export function localProblems(job: JobFields): Partial<Record<keyof JobFields, string>> {
  const problems: Partial<Record<keyof JobFields, string>> = {};
  if (!job.company.trim()) problems.company = 'Add a company.';
  if (!job.title.trim()) problems.title = 'Add a title.';
  if (!job.description.trim()) problems.description = 'Add a description.';
  if (job.deadline && job.deadline < new Date().toISOString().slice(0, 10))
    problems.deadline = 'The deadline has already passed.';
  if (job.stipend_min !== null && job.stipend_max !== null && job.stipend_min > job.stipend_max)
    problems.stipend_max = 'This should not be below the lowest pay.';
  if (job.apply_url && !/^https?:\/\/\S+\.\S+/.test(job.apply_url))
    problems.apply_url = 'Enter a full link that starts with https://';
  return problems;
}

export function useSimilar(job: Pick<JobFields, 'company' | 'title' | 'deadline'>, enabled = true) {
  const params = new URLSearchParams({ company: job.company, title: job.title });
  if (job.deadline) params.set('deadline', job.deadline);
  return useQuery({
    queryKey: ['similar', params.toString()],
    queryFn: () => api<Duplicate[]>(`/admin/jobs/similar?${params}`),
    enabled: enabled && job.company.trim().length > 1 && job.title.trim().length > 3,
  });
}

export function JobForm({
  value,
  onChange,
  problems = {},
  error,
  confidence = {},
}: {
  value: JobFields;
  onChange: (value: JobFields) => void;
  problems?: Partial<Record<string, string>>;
  error?: ApiError | null;
  confidence?: Record<string, Confidence>;
}) {
  const set = <K extends keyof JobFields>(key: K, next: JobFields[K]) =>
    onChange({ ...value, [key]: next });
  const errorFor = (key: keyof JobFields) => problems[key] ?? error?.fieldError(key) ?? null;
  const number = (raw: string) => (raw === '' ? null : Math.max(0, Math.round(Number(raw))));
  const check = (key: string) =>
    confidence[key] === 'low' ? (
      <Badge tone="warning">Check this: not found in the posting</Badge>
    ) : confidence[key] === 'medium' ? (
      <span>Please check. This was inferred.</span>
    ) : undefined;

  return (
    <div className="grid gap-5 sm:grid-cols-2">
      <Field label="Company" required error={errorFor('company')} hint={check('company')}>
        {(ids) => (
          <Input {...ids} value={value.company} onChange={(e) => set('company', e.target.value)} />
        )}
      </Field>
      <Field label="Title" required error={errorFor('title')} hint={check('title')}>
        {(ids) => (
          <Input {...ids} value={value.title} onChange={(e) => set('title', e.target.value)} />
        )}
      </Field>
      <Field label="Type" hint={check('job_type')}>
        {(ids) => (
          <Select
            {...ids}
            value={value.job_type}
            onValueChange={(v) => set('job_type', v as JobFields['job_type'])}
            options={[
              { value: 'internship', label: 'Internship' },
              { value: 'full-time', label: 'Full-time' },
            ]}
          />
        )}
      </Field>
      <Field label="Location" hint={check('location')}>
        {(ids) => (
          <Input
            {...ids}
            value={value.location}
            onChange={(e) => set('location', e.target.value)}
          />
        )}
      </Field>
      <div className="sm:col-span-2">
        <CheckRow
          label="Remote work is possible"
          checked={value.remote}
          onCheckedChange={(v) => set('remote', v)}
        />
      </div>
      <Field
        label="Description"
        required
        className="sm:col-span-2"
        error={errorFor('description')}
        hint={check('description')}
      >
        {(ids) => (
          <Textarea
            {...ids}
            rows={8}
            value={value.description}
            onChange={(e) => set('description', e.target.value)}
          />
        )}
      </Field>
      <Field label="Requirements" className="sm:col-span-2">
        {(ids) => (
          <Textarea
            {...ids}
            rows={3}
            value={value.requirements}
            onChange={(e) => set('requirements', e.target.value)}
          />
        )}
      </Field>
      <Field label="Skills" className="sm:col-span-2" hint={check('skills')}>
        {(ids) => <TagInput {...ids} values={value.skills} onChange={(v) => set('skills', v)} />}
      </Field>
      <Field
        label={
          value.job_type === 'internship' ? 'Lowest stipend (₹ a month)' : 'Lowest pay (₹ a year)'
        }
        error={errorFor('stipend_min')}
        hint={check('stipend_min')}
      >
        {(ids) => (
          <Input
            {...ids}
            type="number"
            min={0}
            inputMode="numeric"
            value={value.stipend_min ?? ''}
            onChange={(e) => set('stipend_min', number(e.target.value))}
          />
        )}
      </Field>
      <Field
        label={
          value.job_type === 'internship' ? 'Highest stipend (₹ a month)' : 'Highest pay (₹ a year)'
        }
        error={errorFor('stipend_max')}
      >
        {(ids) => (
          <Input
            {...ids}
            type="number"
            min={0}
            inputMode="numeric"
            value={value.stipend_max ?? ''}
            onChange={(e) => set('stipend_max', number(e.target.value))}
          />
        )}
      </Field>
      <Field label="Apply by" error={errorFor('deadline')} hint={check('deadline')}>
        {(ids) => (
          <Input
            {...ids}
            type="date"
            value={value.deadline ?? ''}
            onChange={(e) => set('deadline', e.target.value || null)}
          />
        )}
      </Field>
      <Field label="Duration (months)" hint={check('duration_months')}>
        {(ids) => (
          <Input
            {...ids}
            type="number"
            min={1}
            max={36}
            inputMode="numeric"
            value={value.duration_months ?? ''}
            onChange={(e) => set('duration_months', number(e.target.value) || null)}
          />
        )}
      </Field>
      <Field
        label="Apply link"
        className="sm:col-span-2"
        error={errorFor('apply_url')}
        hint={check('apply_url')}
      >
        {(ids) => (
          <Input
            {...ids}
            type="url"
            inputMode="url"
            placeholder="https://"
            value={value.apply_url}
            onChange={(e) => set('apply_url', e.target.value.trim())}
          />
        )}
      </Field>
    </div>
  );
}
