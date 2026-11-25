import { useMutation, useQueryClient } from '@tanstack/react-query';
import { FileText, Plus, ShieldCheck, Trash2, Upload } from 'lucide-react';
import { useRef, useState } from 'react';
import { toast } from 'sonner';
import { TagInput } from '@/components/TagInput';
import { Button } from '@/components/ui/button';
import { Alert } from '@/components/ui/display';
import { CheckRow, Field, Input, Select, Textarea } from '@/components/ui/form';
import { api, messageOf } from '@/lib/api';
import { plural } from '@/lib/format';
import type { ParsedProfile, Preferences, Profile, ResumeResult } from '@/lib/types';
import { locationOptions, roleOptions } from '@/lib/vocabulary';

const parsedByText: Record<ResumeResult['parsed_by'], string> = {
  local: 'Read on our server only. Nothing was sent to an AI provider.',
  mock: 'Read with built-in rules. Nothing was sent to an AI provider.',
  live: 'Read by the AI provider after identifiers were removed.',
  cache: 'Read by the AI provider after identifiers were removed.',
};

export function ResumeUpload({
  profile,
  onParsed,
}: {
  profile: Profile;
  onParsed?: (result: ResumeResult) => void;
}) {
  const client = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [showText, setShowText] = useState(false);
  const upload = useMutation({
    mutationFn: (file: File) => {
      const body = new FormData();
      body.append('file', file);
      return api<ResumeResult>('/profile/resume', { method: 'POST', body });
    },
    onSuccess: (result) => {
      client.setQueryData(['profile'], result);
      client.invalidateQueries({ queryKey: ['home'] });
      onParsed?.(result);
    },
  });
  const remove = useMutation({
    mutationFn: () => api<Profile>('/profile/resume', { method: 'DELETE' }),
    onSuccess: (updated) => {
      client.setQueryData(['profile'], updated);
      upload.reset();
      toast.success('Resume removed');
    },
    onError: (error) => toast.error(messageOf(error)),
  });
  const result = upload.data;
  const removed = result ? Object.values(result.redactions).reduce((a, b) => a + b, 0) : 0;

  return (
    <div className="flex flex-col gap-4">
      {upload.isError && <Alert tone="danger">{messageOf(upload.error)}</Alert>}
      <div className="flex flex-wrap items-center gap-3">
        <input
          ref={input}
          type="file"
          accept=".pdf,.docx"
          className="sr-only"
          tabIndex={-1}
          aria-label="Resume file"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) upload.mutate(file);
            e.target.value = '';
          }}
        />
        <Button onClick={() => input.current?.click()} loading={upload.isPending}>
          <Upload aria-hidden />
          {profile.resume_name ? 'Replace resume' : 'Upload resume'}
        </Button>
        <span className="text-muted-foreground text-sm">PDF or DOCX, up to 5 MB</span>
      </div>
      {profile.resume_name && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <FileText className="size-4" aria-hidden />
          <span className="font-medium break-all">{profile.resume_name}</span>
          <Button variant="ghost" size="sm" onClick={() => setShowText(!showText)}>
            {showText ? 'Hide extracted text' : 'Show extracted text'}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => remove.mutate()}>
            Remove
          </Button>
        </div>
      )}
      {result && (
        <Alert tone="success" title="Resume read">
          {removed > 0
            ? `${plural(removed, 'personal detail')} removed before processing (${Object.entries(
                result.redactions,
              )
                .map(([kind, count]) => `${kind}: ${count}`)
                .join(', ')}). `
            : 'No personal identifiers were found. '}
          {parsedByText[result.parsed_by]}
        </Alert>
      )}
      {showText && profile.resume_text_redacted && (
        <div>
          <p className="text-muted-foreground flex items-center gap-2 text-sm">
            <ShieldCheck className="size-4" aria-hidden />
            This is exactly what is stored and processed.
          </p>
          <pre
            tabIndex={0}
            role="region"
            aria-label="Extracted resume text"
            className="bg-muted mt-2 max-h-72 overflow-y-auto rounded-md p-3 font-sans text-sm break-words whitespace-pre-wrap"
          >
            {profile.resume_text_redacted}
          </pre>
        </div>
      )}
    </div>
  );
}

type ListKey = 'education' | 'projects' | 'experience';

const blank = {
  education: { degree: '', institution: '', year: '' },
  projects: { title: '', summary: '' },
  experience: { role: '', organisation: '', summary: '' },
};

const sectionText: Record<ListKey, { title: string; item: string }> = {
  education: { title: 'Education', item: 'education entry' },
  projects: { title: 'Projects', item: 'project' },
  experience: { title: 'Experience', item: 'experience' },
};

export function ParsedProfileForm({
  value,
  onChange,
}: {
  value: ParsedProfile;
  onChange: (value: ParsedProfile) => void;
}) {
  const section = (key: ListKey) => {
    const rows = value[key] as Record<string, string>[];
    const update = (next: Record<string, string>[]) =>
      onChange({ ...value, [key]: next } as ParsedProfile);
    return (
      <fieldset key={key} className="border-t pt-5">
        <legend className="sr-only">{sectionText[key].title}</legend>
        <div className="flex items-center justify-between">
          <h3 className="font-medium" aria-hidden>
            {sectionText[key].title}
          </h3>
          <Button variant="ghost" size="sm" onClick={() => update([...rows, { ...blank[key] }])}>
            <Plus aria-hidden />
            Add {sectionText[key].item}
          </Button>
        </div>
        <div className="mt-2 flex flex-col gap-4">
          {rows.length === 0 && <p className="text-muted-foreground text-sm">None added.</p>}
          {rows.map((row, index) => (
            <div key={index} className="flex items-start gap-2 rounded-md border p-3">
              <div className="grid flex-1 gap-3 sm:grid-cols-2">
                {Object.keys(blank[key]).map((field) => (
                  <Field
                    key={field}
                    label={field[0].toUpperCase() + field.slice(1)}
                    className={field === 'summary' ? 'sm:col-span-2' : undefined}
                  >
                    {(ids) => {
                      const Control = field === 'summary' ? Textarea : Input;
                      return (
                        <Control
                          {...ids}
                          maxLength={field === 'summary' ? 600 : 200}
                          className={field === 'summary' ? 'min-h-16' : undefined}
                          value={row[field] ?? ''}
                          onChange={(e: { target: { value: string } }) =>
                            update(
                              rows.map((r, i) =>
                                i === index ? { ...r, [field]: e.target.value } : r,
                              ),
                            )
                          }
                        />
                      );
                    }}
                  </Field>
                ))}
              </div>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Remove ${sectionText[key].item} ${index + 1}`}
                onClick={() => update(rows.filter((_, i) => i !== index))}
              >
                <Trash2 aria-hidden />
              </Button>
            </div>
          ))}
        </div>
      </fieldset>
    );
  };
  return (
    <div className="flex flex-col gap-5">
      <Field label="Skills" hint="Used for matching. Common aliases are merged for you.">
        {(ids) => (
          <TagInput
            {...ids}
            values={value.skills}
            onChange={(skills) => onChange({ ...value, skills })}
          />
        )}
      </Field>
      {(['education', 'projects', 'experience'] as const).map(section)}
    </div>
  );
}

export function PreferencesForm({
  value,
  onChange,
}: {
  value: Preferences;
  onChange: (value: Preferences) => void;
}) {
  const set = <K extends keyof Preferences>(key: K, next: Preferences[K]) =>
    onChange({ ...value, [key]: next });
  const toggleType = (type: 'internship' | 'full-time', on: boolean) =>
    set('job_types', on ? [...value.job_types, type] : value.job_types.filter((t) => t !== type));

  return (
    <div className="grid gap-5 sm:grid-cols-2">
      <Field label="Roles" className="sm:col-span-2" hint="Pick from the list or type your own.">
        {(ids) => (
          <TagInput
            {...ids}
            values={value.roles}
            onChange={(v) => set('roles', v)}
            suggestions={roleOptions}
            itemName="role"
          />
        )}
      </Field>
      <Field label="Locations" className="sm:col-span-2">
        {(ids) => (
          <TagInput
            {...ids}
            values={value.locations}
            onChange={(v) => set('locations', v)}
            suggestions={locationOptions}
            itemName="city"
          />
        )}
      </Field>
      <fieldset>
        <legend className="text-sm font-medium">Job types</legend>
        <CheckRow
          label="Internship"
          checked={value.job_types.includes('internship')}
          onCheckedChange={(on) => toggleType('internship', on)}
        />
        <CheckRow
          label="Full-time"
          checked={value.job_types.includes('full-time')}
          onCheckedChange={(on) => toggleType('full-time', on)}
        />
      </fieldset>
      <div>
        <p className="text-sm font-medium">Remote</p>
        <CheckRow
          label="Remote work is fine"
          checked={value.remote_ok}
          onCheckedChange={(on) => set('remote_ok', on)}
        />
      </div>
      <Field label="Internship length">
        {(ids) => (
          <Select
            {...ids}
            value={String(value.duration ?? 0)}
            onValueChange={(v) => set('duration', Number(v) || null)}
            options={[
              { value: '0', label: 'Any length' },
              { value: '2', label: 'About 2 months' },
              { value: '3', label: 'About 3 months' },
              { value: '6', label: 'About 6 months' },
              { value: '12', label: 'About 12 months' },
            ]}
          />
        )}
      </Field>
      <Field label="Start" hint="For example, summer 2027.">
        {(ids) => (
          <Input
            {...ids}
            maxLength={200}
            value={value.start_window}
            onChange={(e) => set('start_window', e.target.value)}
          />
        )}
      </Field>
      <Field label="Lowest stipend (₹ a month)">
        {(ids) => (
          <Input
            {...ids}
            type="number"
            min={0}
            step={1000}
            inputMode="numeric"
            value={value.min_stipend ?? ''}
            onChange={(e) => set('min_stipend', e.target.value ? Number(e.target.value) : null)}
          />
        )}
      </Field>
    </div>
  );
}

export function useSaveProfile() {
  const client = useQueryClient();
  const onSuccess = (updated: Profile) => {
    client.setQueryData(['profile'], updated);
    for (const key of ['home', 'search', 'saved', 'job'])
      client.invalidateQueries({ queryKey: [key] });
  };
  const onError = (error: unknown) => {
    toast.error(messageOf(error));
  };
  return {
    profile: useMutation({
      mutationFn: (parsed_profile: ParsedProfile) =>
        api<Profile>('/profile', { method: 'PUT', body: { parsed_profile } }),
      onSuccess,
      onError,
    }),
    preferences: useMutation({
      mutationFn: (body: Preferences) =>
        api<Profile>('/profile/preferences', { method: 'PUT', body }),
      onSuccess,
      onError,
    }),
  };
}
