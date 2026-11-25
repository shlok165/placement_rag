import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Briefcase, PlusCircle, Search, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { toast } from 'sonner';
import { Pagination } from '@/components/Pagination';
import { QueryState } from '@/components/QueryState';
import { StatusBadge, statusLabel } from '@/components/StatusBadge';
import { Button } from '@/components/ui/button';
import { Card, EmptyState, PageHeader } from '@/components/ui/display';
import { Checkbox, Field, Input, Select } from '@/components/ui/form';
import { ConfirmDialog } from '@/components/ui/overlay';
import { api, messageOf } from '@/lib/api';
import { formatDate, formatDateTime, plural } from '@/lib/format';
import { useTitle } from '@/lib/title';
import type { AdminJobRow, JobStatus, Page } from '@/lib/types';

const statuses: JobStatus[] = ['draft', 'pending', 'indexed', 'failed', 'expired', 'archived'];

export function PostingsPage() {
  useTitle('Postings');
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [selected, setSelected] = useState<number[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [text, setText] = useState(params.get('q') ?? '');

  const get = (key: string, fallback = '') => params.get(key) ?? fallback;
  const update = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries({ page: '', ...changes })) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setParams(next, { replace: true });
    setSelected([]);
  };

  useEffect(() => {
    if (text === (params.get('q') ?? '')) return;
    const timer = setTimeout(() => update({ q: text }), 250);
    return () => clearTimeout(timer);
    // `update` only reads the current params, which are already a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, params]);

  const query = useQuery({
    queryKey: ['admin-jobs', params.toString()],
    queryFn: ({ signal }) => api<Page<AdminJobRow>>(`/admin/jobs?${params}`, { signal }),
    placeholderData: keepPreviousData,
    refetchInterval: (q) =>
      q.state.data?.items.some((job) => job.status === 'pending') ? 2000 : false,
  });
  const companies = useQuery({
    queryKey: ['companies'],
    queryFn: () => api<string[]>('/admin/jobs/companies'),
  });

  const bulk = useMutation({
    mutationFn: (action: 'archive' | 'retry') =>
      api<{ done: number; skipped: number }>('/admin/jobs/bulk', {
        method: 'POST',
        body: { ids: selected, action },
      }),
    onSuccess: ({ done, skipped }, action) => {
      const verb = action === 'archive' ? 'archived' : 'queued again';
      const ids = selected;
      toast.success(
        `${plural(done, 'posting')} ${verb}${skipped ? `, ${skipped} skipped` : ''}`,
        action === 'archive' && done
          ? {
              action: {
                label: 'Undo',
                onClick: () =>
                  Promise.allSettled(
                    ids.map((id) => api(`/admin/jobs/${id}/restore`, { method: 'POST' })),
                  ).then(() => client.invalidateQueries({ queryKey: ['admin-jobs'] })),
              },
            }
          : undefined,
      );
      setSelected([]);
      client.invalidateQueries({ queryKey: ['admin-jobs'] });
    },
    onError: (error) => toast.error(messageOf(error)),
  });

  const chips: [string, string][] = [];
  if (get('q')) chips.push(['q', `Search: ${get('q')}`]);
  if (get('status')) chips.push(['status', statusLabel(get('status') as JobStatus)]);
  if (get('company')) chips.push(['company', get('company')]);
  if (get('deadline_from'))
    chips.push(['deadline_from', `From ${formatDate(get('deadline_from'))}`]);
  if (get('deadline_to')) chips.push(['deadline_to', `Until ${formatDate(get('deadline_to'))}`]);

  const items = query.data?.items ?? [];
  const allSelected = items.length > 0 && items.every((job) => selected.includes(job.id));
  const failedSelected = items.some((job) => selected.includes(job.id) && job.status === 'failed');
  const toggle = (id: number, on: boolean) =>
    setSelected(on ? [...selected, id] : selected.filter((other) => other !== id));

  return (
    <>
      <PageHeader
        title="Postings"
        description="Every internship and job in the portal, including drafts and closed ones."
        actions={
          <Button asChild>
            <Link to="/admin/postings/new">
              <PlusCircle aria-hidden />
              Add posting
            </Link>
          </Button>
        }
      />
      <Card className="mb-4 p-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <Field label="Search" className="sm:col-span-2">
            {(ids) => (
              <div className="relative">
                <Search
                  className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2"
                  aria-hidden
                />
                <Input
                  {...ids}
                  type="search"
                  data-search-input
                  className="pl-9"
                  placeholder="Title, company or place"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                />
              </div>
            )}
          </Field>
          <Field label="Status">
            {(ids) => (
              <Select
                {...ids}
                value={get('status', 'all')}
                onValueChange={(v) => update({ status: v === 'all' ? '' : v })}
                options={[
                  { value: 'all', label: 'All' },
                  ...statuses.map((s) => ({ value: s, label: statusLabel(s) })),
                ]}
              />
            )}
          </Field>
          <Field label="Company">
            {(ids) => (
              <Select
                {...ids}
                value={get('company', 'all')}
                onValueChange={(v) => update({ company: v === 'all' ? '' : v })}
                options={[
                  { value: 'all', label: 'All' },
                  ...(companies.data ?? []).map((c) => ({ value: c, label: c })),
                ]}
              />
            )}
          </Field>
          <Field label="Deadline from">
            {(ids) => (
              <Input
                {...ids}
                type="date"
                value={get('deadline_from')}
                onChange={(e) => update({ deadline_from: e.target.value })}
              />
            )}
          </Field>
          <Field label="Sort by">
            {(ids) => (
              <Select
                {...ids}
                value={get('sort', 'updated')}
                onValueChange={(v) => update({ sort: v === 'updated' ? '' : v })}
                options={[
                  { value: 'updated', label: 'Recently changed' },
                  { value: 'deadline', label: 'Deadline' },
                  { value: 'company', label: 'Company' },
                  { value: 'title', label: 'Title' },
                  { value: 'status', label: 'Status' },
                ]}
              />
            )}
          </Field>
        </div>
        {chips.length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-2" aria-label="Active filters">
            {chips.map(([key, label]) => (
              <li key={key}>
                <button
                  type="button"
                  className="bg-accent text-accent-foreground flex min-h-8 items-center gap-1 rounded-full px-3 text-sm"
                  onClick={() => {
                    if (key === 'q') setText('');
                    update({ [key]: '' });
                  }}
                >
                  {label}
                  <X className="size-3.5" aria-hidden />
                  <span className="sr-only">Remove filter</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {selected.length > 0 && (
        <div
          role="region"
          aria-label="Bulk actions"
          className="bg-accent text-accent-foreground sticky top-16 z-20 mb-3 flex flex-wrap items-center gap-2 rounded-md px-4 py-2 text-sm"
        >
          <span className="mr-auto font-medium">{plural(selected.length, 'posting')} selected</span>
          <Button
            variant="secondary"
            size="sm"
            disabled={!failedSelected}
            title={failedSelected ? undefined : 'Select at least one failed posting'}
            onClick={() => bulk.mutate('retry')}
          >
            Retry failed
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setConfirming(true)}>
            Archive
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setSelected([])}>
            Clear
          </Button>
        </div>
      )}

      <QueryState query={query}>
        {(page) =>
          page.items.length === 0 ? (
            <EmptyState
              icon={Briefcase}
              title={chips.length ? 'No postings match these filters' : 'No postings yet'}
              action={
                chips.length ? (
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setText('');
                      setParams({});
                    }}
                  >
                    Clear filters
                  </Button>
                ) : (
                  <Button asChild>
                    <Link to="/admin/postings/new">Add the first posting</Link>
                  </Button>
                )
              }
            >
              {chips.length
                ? 'Remove a filter or try a shorter search.'
                : 'Add one with the form, paste the text, upload a file or import a CSV.'}
            </EmptyState>
          ) : (
            <>
              <p className="text-muted-foreground mb-2 text-sm" aria-live="polite">
                {plural(page.total, 'posting')}
              </p>
              <Card className="hidden overflow-x-auto md:block">
                <table className="w-full text-sm">
                  <caption className="sr-only">Postings</caption>
                  <thead>
                    <tr className="text-muted-foreground border-b text-left">
                      <th scope="col" className="w-12 p-3">
                        <Checkbox
                          aria-label="Select all on this page"
                          checked={allSelected}
                          onCheckedChange={(on) => setSelected(on ? items.map((j) => j.id) : [])}
                        />
                      </th>
                      <th scope="col" className="p-3 font-medium">
                        Posting
                      </th>
                      <th scope="col" className="p-3 font-medium">
                        Location
                      </th>
                      <th scope="col" className="p-3 font-medium">
                        Deadline
                      </th>
                      <th scope="col" className="p-3 font-medium">
                        Status
                      </th>
                      <th scope="col" className="p-3 font-medium">
                        Changed
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.items.map((job) => (
                      <tr key={job.id} className="hover:bg-muted/60 border-b last:border-0">
                        <td className="p-3">
                          <Checkbox
                            aria-label={`Select ${job.title || `posting ${job.id}`}`}
                            checked={selected.includes(job.id)}
                            onCheckedChange={(on) => toggle(job.id, on === true)}
                          />
                        </td>
                        <td className="max-w-80 p-3">
                          <Link
                            to={`/admin/postings/${job.id}`}
                            className="font-medium underline-offset-4 hover:underline"
                          >
                            {job.title || `Untitled posting #${job.id}`}
                          </Link>
                          <p className="text-muted-foreground">
                            {job.company || 'Company not set'}
                            {job.duplicate_of_id && ' · Possible duplicate'}
                          </p>
                        </td>
                        <td className="p-3">{job.location || '–'}</td>
                        <td className="p-3 whitespace-nowrap">{formatDate(job.deadline)}</td>
                        <td className="p-3">
                          <StatusBadge status={job.status} review={job.needs_review} />
                          {job.last_error && (
                            <p className="text-danger mt-1 max-w-56 text-xs">{job.last_error}</p>
                          )}
                        </td>
                        <td className="text-muted-foreground p-3 whitespace-nowrap">
                          {formatDateTime(job.updated_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
              <ul className="flex flex-col gap-3 md:hidden">
                {page.items.map((job) => (
                  <li key={job.id}>
                    <Card className="flex gap-3 p-4">
                      <Checkbox
                        aria-label={`Select ${job.title || `posting ${job.id}`}`}
                        checked={selected.includes(job.id)}
                        onCheckedChange={(on) => toggle(job.id, on === true)}
                      />
                      <div className="min-w-0 flex-1">
                        <Link to={`/admin/postings/${job.id}`} className="font-medium">
                          {job.title || `Untitled posting #${job.id}`}
                        </Link>
                        <p className="text-muted-foreground text-sm">
                          {[job.company, job.location].filter(Boolean).join(' · ')}
                        </p>
                        <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                          <StatusBadge status={job.status} review={job.needs_review} />
                          {formatDate(job.deadline)}
                        </p>
                        {job.last_error && (
                          <p className="text-danger mt-1 text-xs">{job.last_error}</p>
                        )}
                      </div>
                    </Card>
                  </li>
                ))}
              </ul>
              <Pagination
                page={page.page}
                pageSize={page.page_size}
                total={page.total}
                onChange={(p) => update({ page: String(p) })}
              />
            </>
          )
        }
      </QueryState>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`Archive ${plural(selected.length, 'posting')}?`}
        description="Students stop seeing them at once. You can undo this."
        confirmLabel="Archive"
        destructive
        onConfirm={() => bulk.mutate('archive')}
      />
    </>
  );
}
