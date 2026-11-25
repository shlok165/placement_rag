import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Archive, Clock, FileDown, MoreHorizontal, RefreshCw, Trash2, Undo2 } from 'lucide-react';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { toast } from 'sonner';
import { DuplicateWarning } from './DuplicateWarning';
import { JobForm, localProblems, pickFields } from './JobForm';
import { Breadcrumb } from '@/components/Breadcrumb';
import { QueryState } from '@/components/QueryState';
import { StatusBadge } from '@/components/StatusBadge';
import { Button } from '@/components/ui/button';
import { Alert, Card, PageHeader, Progress } from '@/components/ui/display';
import { ConfirmDialog, Menu, MenuContent, MenuItem, MenuTrigger } from '@/components/ui/overlay';
import { api, ApiError, messageOf } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { useTitle } from '@/lib/title';
import type { AdminJob, JobFields } from '@/lib/types';

type Verb = 'publish' | 'retry' | 'reindex' | 'archive' | 'expire' | 'restore';

const doneText: Record<Verb, string> = {
  publish: 'Publishing. It will be live shortly.',
  retry: 'Trying again',
  reindex: 'Rebuilding the search entry',
  archive: 'Posting archived',
  expire: 'Posting marked as expired',
  restore: 'Posting restored',
};

type HistoryEntry = {
  id: number;
  action: string;
  actor: string | null;
  diff: Record<string, { from?: unknown; to?: unknown } | unknown>;
  created_at: string;
};

const actionText: Record<string, string> = {
  created: 'Added',
  edited: 'Edited',
  published: 'Published',
  retried: 'Retried',
  reindexed: 'Search entry rebuilt',
  archived: 'Archived',
  expired: 'Expired',
  restored: 'Restored',
};

function shown(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'empty';
  if (Array.isArray(value)) return value.join(', ') || 'empty';
  const text = String(value);
  return text.length > 80 ? `${text.slice(0, 80)}…` : text;
}

function History({ id }: { id: number }) {
  const query = useQuery({
    queryKey: ['job-history', id],
    queryFn: () => api<HistoryEntry[]>(`/admin/jobs/${id}/history`),
  });
  return (
    <Card className="p-5">
      <h2 className="font-semibold">Change history</h2>
      <QueryState query={query}>
        {(entries) => (
          <ol className="mt-3 flex flex-col gap-4 text-sm">
            {entries.map((entry) => (
              <li key={entry.id} className="border-l-2 pl-3">
                <p>
                  <span className="font-medium">{actionText[entry.action] ?? entry.action}</span>{' '}
                  <span className="text-muted-foreground">
                    by {entry.actor ?? 'the system'}, {formatDateTime(entry.created_at)}
                  </span>
                </p>
                {entry.action === 'edited' && (
                  <ul className="text-muted-foreground mt-1">
                    {Object.entries(entry.diff).map(([field, change]) => {
                      const { from, to } = change as { from: unknown; to: unknown };
                      return (
                        <li key={field} className="break-words">
                          <span className="text-foreground">{field.replaceAll('_', ' ')}</span>:{' '}
                          {shown(from)} → {shown(to)}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </li>
            ))}
          </ol>
        )}
      </QueryState>
    </Card>
  );
}

function Editor({ job }: { job: AdminJob }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [fields, setFields] = useState<JobFields>(pickFields(job));
  const [showProblems, setShowProblems] = useState(false);
  const [confirming, setConfirming] = useState<'archive' | 'expire' | 'delete' | null>(null);

  const saved = pickFields(job);
  const dirty = JSON.stringify(saved) !== JSON.stringify(fields);
  const problems = localProblems(fields);
  const blocked = Object.keys(problems).length > 0;
  const reviewing = job.status === 'draft' && job.parse_meta.needs_review;

  const apply = (updated: AdminJob) => {
    client.setQueryData(['admin-job', job.id], updated);
    client.invalidateQueries({ queryKey: ['admin-jobs'] });
    client.invalidateQueries({ queryKey: ['job-history', job.id] });
  };

  const save = useMutation({
    mutationFn: () => api<AdminJob>(`/admin/jobs/${job.id}`, { method: 'PATCH', body: fields }),
    onSuccess: (updated) => {
      apply(updated);
      setFields(pickFields(updated));
    },
  });
  const act = useMutation({
    mutationFn: (verb: Verb) => api<AdminJob>(`/admin/jobs/${job.id}/${verb}`, { method: 'POST' }),
    onSuccess: (updated, verb) => {
      apply(updated);
      toast.success(
        doneText[verb],
        verb === 'archive' || verb === 'expire'
          ? { action: { label: 'Undo', onClick: () => act.mutate('restore') } }
          : undefined,
      );
    },
    onError: (error) => toast.error(messageOf(error)),
  });
  const remove = useMutation({
    mutationFn: () => api<void>(`/admin/jobs/${job.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Posting deleted');
      client.invalidateQueries({ queryKey: ['admin-jobs'] });
      navigate('/admin/postings');
    },
    onError: (error) => toast.error(messageOf(error)),
  });

  const saveOnly = () => {
    if (job.status === 'indexed') {
      setShowProblems(true);
      if (blocked) return;
    }
    save.mutate(undefined, { onSuccess: () => toast.success('Changes saved') });
  };
  const publish = async () => {
    setShowProblems(true);
    if (blocked) return;
    if (dirty) await save.mutateAsync();
    act.mutate('publish');
  };

  const error = save.error ?? act.error;
  const canPublish = job.status === 'draft' || job.status === 'failed';
  const canDelete = ['draft', 'failed', 'archived'].includes(job.status);

  if (job.status === 'pending') {
    return (
      <Card className="p-6">
        <div role="status" className="flex flex-col gap-3">
          <p className="font-medium">
            {job.title ? 'Adding this posting to search' : 'Reading the posting'}
          </p>
          <Progress value={60} label="Processing" />
          <p className="text-muted-foreground text-sm">
            This usually takes a few seconds. The page updates by itself.
          </p>
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {job.last_error && (
        <Alert
          tone="danger"
          title="This posting could not be processed"
          action={
            job.status === 'failed' && (
              <Button variant="secondary" size="sm" onClick={() => act.mutate('retry')}>
                <RefreshCw aria-hidden />
                Retry
              </Button>
            )
          }
        >
          {job.last_error}
        </Alert>
      )}
      {reviewing && (
        <Alert tone="info" title="Review before publishing">
          Compare the fields with the original text. Highlighted fields were not found or were
          inferred.
        </Alert>
      )}
      <DuplicateWarning duplicates={job.duplicates} />
      <div className={job.raw_text ? 'grid items-start gap-6 xl:grid-cols-[2fr_3fr]' : undefined}>
        {job.raw_text && (
          <Card className="p-5 xl:sticky xl:top-20">
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-semibold">Original text</h2>
              {job.file_name && (
                <Button variant="ghost" size="sm" asChild>
                  <a href={`/api/admin/jobs/${job.id}/file`}>
                    <FileDown aria-hidden />
                    {job.file_name}
                  </a>
                </Button>
              )}
            </div>
            <pre
              tabIndex={0}
              role="region"
              aria-label="Original text"
              className="bg-muted mt-3 max-h-[28rem] overflow-y-auto rounded-md p-3 font-sans text-sm break-words whitespace-pre-wrap"
            >
              {job.raw_text}
            </pre>
          </Card>
        )}
        <Card className="p-5">
          <h2 className="mb-4 font-semibold">Posting details</h2>
          {error && <Alert tone="danger" title={messageOf(error)} className="mb-4" />}
          <JobForm
            value={fields}
            onChange={setFields}
            problems={showProblems ? problems : {}}
            error={error instanceof ApiError ? error : null}
            confidence={reviewing ? job.parse_meta.confidence : {}}
          />
          <div className="bg-card sticky bottom-0 -mx-5 mt-6 -mb-5 flex flex-wrap items-center gap-2 rounded-b-lg border-t px-5 py-3">
            {canPublish && (
              <Button onClick={publish} loading={act.isPending || save.isPending}>
                Publish
              </Button>
            )}
            <Button
              variant={canPublish ? 'secondary' : 'primary'}
              onClick={saveOnly}
              disabled={!dirty}
              title={dirty ? undefined : 'Nothing to save yet'}
              loading={save.isPending}
            >
              {job.status === 'draft' ? 'Save draft' : 'Save changes'}
            </Button>
            {dirty && (
              <Button variant="ghost" onClick={() => setFields(saved)}>
                Discard changes
              </Button>
            )}
            <span className="text-muted-foreground text-sm" aria-live="polite">
              {dirty ? 'Unsaved changes' : 'All changes saved'}
            </span>
            <Menu>
              <MenuTrigger asChild>
                <Button variant="ghost" size="icon" className="ml-auto" aria-label="More actions">
                  <MoreHorizontal aria-hidden />
                </Button>
              </MenuTrigger>
              <MenuContent>
                {job.status === 'indexed' && (
                  <>
                    <MenuItem onSelect={() => act.mutate('reindex')}>
                      <RefreshCw aria-hidden />
                      Rebuild search entry
                    </MenuItem>
                    <MenuItem onSelect={() => setConfirming('expire')}>
                      <Clock aria-hidden />
                      Mark as expired
                    </MenuItem>
                  </>
                )}
                {(job.status === 'archived' || job.status === 'expired') && (
                  <MenuItem onSelect={() => act.mutate('restore')}>
                    <Undo2 aria-hidden />
                    Restore
                  </MenuItem>
                )}
                {job.status !== 'archived' && (
                  <MenuItem onSelect={() => setConfirming('archive')}>
                    <Archive aria-hidden />
                    Archive
                  </MenuItem>
                )}
                {canDelete && (
                  <MenuItem destructive onSelect={() => setConfirming('delete')}>
                    <Trash2 aria-hidden />
                    Delete permanently
                  </MenuItem>
                )}
              </MenuContent>
            </Menu>
          </div>
        </Card>
      </div>
      <History id={job.id} />
      <ConfirmDialog
        open={confirming === 'archive' || confirming === 'expire'}
        onOpenChange={(open) => !open && setConfirming(null)}
        title={confirming === 'archive' ? 'Archive this posting?' : 'Mark as expired?'}
        description="Students stop seeing it in search at once. You can undo this."
        confirmLabel={confirming === 'archive' ? 'Archive' : 'Mark as expired'}
        destructive
        onConfirm={() => confirming && act.mutate(confirming as Verb)}
      />
      <ConfirmDialog
        open={confirming === 'delete'}
        onOpenChange={(open) => !open && setConfirming(null)}
        title="Delete this posting permanently?"
        description="The posting, its file and any student saves or applications for it are removed. This cannot be undone."
        confirmLabel="Delete permanently"
        destructive
        onConfirm={() => remove.mutate()}
      />
    </div>
  );
}

export function PostingDetailPage() {
  const id = Number(useParams().id);
  const query = useQuery({
    queryKey: ['admin-job', id],
    queryFn: () => api<AdminJob>(`/admin/jobs/${id}`),
    refetchInterval: (q) => (q.state.data?.status === 'pending' ? 1200 : false),
  });
  const job = query.data;
  const title = job?.title || `Posting #${id}`;
  useTitle(title);
  return (
    <>
      <PageHeader
        breadcrumb={<Breadcrumb items={[['/admin/postings', 'Postings']]} current={title} />}
        title={title}
        description={job?.company}
        actions={
          job && (
            <StatusBadge
              status={job.status}
              review={job.status === 'draft' && job.parse_meta.needs_review}
            />
          )
        }
      />
      <QueryState query={query}>
        {(data) => <Editor key={`${data.id}:${data.status}`} job={data} />}
      </QueryState>
    </>
  );
}
