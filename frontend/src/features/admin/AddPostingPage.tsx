import { useMutation, useQueryClient } from '@tanstack/react-query';
import { FileUp, TriangleAlert } from 'lucide-react';
import { useEffect, useState, type DragEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { toast } from 'sonner';
import { DuplicateWarning } from './DuplicateWarning';
import { emptyJob, JobForm, localProblems, useSimilar } from './JobForm';
import { Breadcrumb } from '@/components/Breadcrumb';
import { Button } from '@/components/ui/button';
import {
  Alert,
  Card,
  PageHeader,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/display';
import { CheckRow, Field, Textarea } from '@/components/ui/form';
import { api, ApiError, messageOf } from '@/lib/api';
import { plural } from '@/lib/format';
import { useTitle } from '@/lib/title';
import type { AdminJob } from '@/lib/types';

const DRAFT_KEY = 'posting-draft';

function loadDraft() {
  try {
    return { ...emptyJob, ...JSON.parse(localStorage.getItem(DRAFT_KEY) ?? '{}') };
  } catch {
    return emptyJob;
  }
}

function storeDraft(value: unknown) {
  try {
    if (value) localStorage.setItem(DRAFT_KEY, JSON.stringify(value));
    else localStorage.removeItem(DRAFT_KEY);
  } catch {
    // Without storage the form still works; it just is not kept between visits.
  }
}

function SubmitError({ error }: { error: unknown }) {
  if (!error) return null;
  const details = error instanceof ApiError ? (error.details as { job_id?: number } | null) : null;
  return (
    <Alert tone="danger" title={messageOf(error)} className="mb-4">
      {details?.job_id && (
        <Link className="underline" to={`/admin/postings/${details.job_id}`}>
          Open posting #{details.job_id}
        </Link>
      )}
    </Alert>
  );
}

function useFinish() {
  const client = useQueryClient();
  const navigate = useNavigate();
  return (job: AdminJob, message: string) => {
    client.invalidateQueries({ queryKey: ['admin-jobs'] });
    toast.success(message);
    navigate(`/admin/postings/${job.id}`);
  };
}

function FormTab() {
  const finish = useFinish();
  const [job, setJob] = useState(loadDraft);
  const [showProblems, setShowProblems] = useState(false);
  const similar = useSimilar(job);
  const problems = localProblems(job);

  useEffect(() => {
    const timer = setTimeout(
      () => storeDraft(JSON.stringify(job) === JSON.stringify(emptyJob) ? null : job),
      400,
    );
    return () => clearTimeout(timer);
  }, [job]);

  const save = useMutation({
    mutationFn: (action: 'draft' | 'publish') =>
      api<AdminJob>('/admin/jobs', { method: 'POST', body: { ...job, action } }),
    onSuccess: (created, action) => {
      storeDraft(null);
      finish(created, action === 'draft' ? 'Draft saved' : 'Publishing. It will be live shortly.');
    },
  });

  const publish = () => {
    setShowProblems(true);
    if (Object.keys(problems).length === 0) save.mutate('publish');
  };

  return (
    <Card className="p-5">
      <SubmitError error={save.error} />
      <DuplicateWarning duplicates={similar.data ?? []} />
      <JobForm
        value={job}
        onChange={setJob}
        problems={showProblems ? problems : {}}
        error={save.error instanceof ApiError ? save.error : null}
      />
      <div className="mt-6 flex flex-wrap items-center gap-2">
        <Button onClick={publish} loading={save.isPending && save.variables === 'publish'}>
          Publish
        </Button>
        <Button
          variant="secondary"
          onClick={() => save.mutate('draft')}
          loading={save.isPending && save.variables === 'draft'}
        >
          Save draft
        </Button>
        <Button variant="ghost" onClick={() => setJob(emptyJob)}>
          Clear form
        </Button>
        <span className="text-muted-foreground text-sm">
          Your entries are kept on this device until you save.
        </span>
      </div>
    </Card>
  );
}

const autoPublishRow = (checked: boolean, onChange: (v: boolean) => void) => (
  <CheckRow
    label="Publish automatically when parsing succeeds"
    hint="Skips review, unless key fields are missing or a likely duplicate exists."
    checked={checked}
    onCheckedChange={onChange}
  />
);

function PasteTab() {
  const finish = useFinish();
  const [text, setText] = useState('');
  const [auto, setAuto] = useState(false);
  const short = text.trim().length < 40;
  const save = useMutation({
    mutationFn: () =>
      api<AdminJob>('/admin/jobs/paste', { method: 'POST', body: { text, auto_publish: auto } }),
    onSuccess: (job) => finish(job, 'Reading the posting'),
  });
  return (
    <Card className="flex flex-col gap-4 p-5">
      <SubmitError error={save.error} />
      <Field label="Posting text" hint="Paste the full message or job description.">
        {(ids) => (
          <Textarea {...ids} rows={14} value={text} onChange={(e) => setText(e.target.value)} />
        )}
      </Field>
      {autoPublishRow(auto, setAuto)}
      <div className="flex items-center gap-3">
        <Button onClick={() => save.mutate()} disabled={short} loading={save.isPending}>
          Read posting
        </Button>
        {short && (
          <span className="text-muted-foreground text-sm">Paste at least 40 characters.</span>
        )}
      </div>
    </Card>
  );
}

function FilePicker({
  accept,
  hint,
  file,
  onPick,
}: {
  accept: string;
  hint: string;
  file: File | null;
  onPick: (file: File | null) => void;
}) {
  const [over, setOver] = useState(false);
  const drop = (event: DragEvent) => {
    event.preventDefault();
    setOver(false);
    onPick(event.dataTransfer.files[0] ?? null);
  };
  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={drop}
      className={`focus-within:outline-ring flex min-h-40 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 text-center focus-within:outline-2 focus-within:outline-offset-2 ${over ? 'border-primary bg-accent' : ''}`}
    >
      <FileUp className="text-muted-foreground size-8" aria-hidden />
      <span className="font-medium">{file ? file.name : 'Choose a file or drop it here'}</span>
      <span className="text-muted-foreground text-sm">{hint}</span>
      <input
        type="file"
        accept={accept}
        className="sr-only"
        onChange={(e) => onPick(e.target.files?.[0] ?? null)}
      />
    </label>
  );
}

function UploadTab() {
  const finish = useFinish();
  const [file, setFile] = useState<File | null>(null);
  const [auto, setAuto] = useState(false);
  const save = useMutation({
    mutationFn: () => {
      const body = new FormData();
      body.append('file', file!);
      body.append('auto_publish', String(auto));
      return api<AdminJob>('/admin/jobs/upload', { method: 'POST', body });
    },
    onSuccess: (job) => finish(job, 'File uploaded. Reading the posting.'),
  });
  return (
    <Card className="flex flex-col gap-4 p-5">
      <SubmitError error={save.error} />
      <FilePicker
        accept=".pdf,.docx"
        hint="PDF or DOCX, up to 5 MB"
        file={file}
        onPick={(picked) => {
          setFile(picked);
          save.reset();
        }}
      />
      {autoPublishRow(auto, setAuto)}
      <Button
        className="self-start"
        onClick={() => save.mutate()}
        disabled={!file}
        title={file ? undefined : 'Choose a file first'}
        loading={save.isPending}
      >
        Upload and read
      </Button>
    </Card>
  );
}

type CsvResult = {
  created: number;
  duplicates: number;
  invalid: number;
  rows: { row: number; status: string; message: string; job_id: number | null }[];
};

function CsvTab() {
  const client = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [publish, setPublish] = useState(true);
  const run = useMutation({
    mutationFn: () => {
      const body = new FormData();
      body.append('file', file!);
      body.append('publish', String(publish));
      return api<CsvResult>('/admin/jobs/csv', { method: 'POST', body });
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ['admin-jobs'] }),
  });
  return (
    <Card className="flex flex-col gap-4 p-5">
      <SubmitError error={run.error} />
      <FilePicker
        accept=".csv,text/csv"
        hint="Columns: company, title, description, and optionally skills, location, remote, job_type, deadline, stipend_min, stipend_max, duration_months, apply_url, requirements"
        file={file}
        onPick={(picked) => {
          setFile(picked);
          run.reset();
        }}
      />
      <CheckRow
        label="Publish valid rows"
        hint="Turn this off to import them as drafts."
        checked={publish}
        onCheckedChange={setPublish}
      />
      <Button
        className="self-start"
        onClick={() => run.mutate()}
        disabled={!file}
        title={file ? undefined : 'Choose a file first'}
        loading={run.isPending}
      >
        Import
      </Button>
      {run.data && (
        <div role="status">
          <Alert
            tone={run.data.invalid || run.data.duplicates ? 'warning' : 'success'}
            title={`${plural(run.data.created, 'posting')} added, ${plural(run.data.duplicates, 'duplicate')} skipped, ${plural(run.data.invalid, 'row')} with problems`}
          />
          <ul className="mt-3 divide-y text-sm">
            {run.data.rows
              .filter((r) => r.status !== 'created' || r.message !== 'Added')
              .map((r) => (
                <li key={r.row} className="flex flex-wrap gap-x-3 py-2">
                  <span className="font-medium">Row {r.row}</span>
                  <span className="flex items-center gap-1">
                    <TriangleAlert className="text-warning size-4" aria-hidden />
                    {r.message}
                  </span>
                  {r.job_id && (
                    <Link className="text-primary underline" to={`/admin/postings/${r.job_id}`}>
                      Open
                    </Link>
                  )}
                </li>
              ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

const tabs = [
  { key: 'form', label: 'Form', content: FormTab },
  { key: 'paste', label: 'Paste text', content: PasteTab },
  { key: 'upload', label: 'Upload file', content: UploadTab },
  { key: 'csv', label: 'CSV import', content: CsvTab },
];

export function AddPostingPage() {
  useTitle('Add posting');
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'form';
  return (
    <>
      <PageHeader
        breadcrumb={<Breadcrumb items={[['/admin/postings', 'Postings']]} current="Add posting" />}
        title="Add posting"
        description="Pick the quickest way in. Pasted text and files are read for you and shown for review before anything goes live."
      />
      <Tabs value={tab} onValueChange={(v) => setParams({ tab: v }, { replace: true })}>
        <TabsList aria-label="How to add">
          {tabs.map(({ key, label }) => (
            <TabsTrigger key={key} value={key}>
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabs.map(({ key, content: Content }) => (
          <TabsContent key={key} value={key} className="mt-4">
            <Content />
          </TabsContent>
        ))}
      </Tabs>
    </>
  );
}
