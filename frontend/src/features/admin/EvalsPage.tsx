import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FlaskConical, Pencil, Play, Plus, ThumbsDown, ThumbsUp, Trash2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router';
import { toast } from 'sonner';
import { Pagination } from '@/components/Pagination';
import { QueryState } from '@/components/QueryState';
import { TagInput } from '@/components/TagInput';
import { Button } from '@/components/ui/button';
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  PageHeader,
  Progress,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/display';
import { Field, Input, Select, Textarea } from '@/components/ui/form';
import { ConfirmDialog, Dialog } from '@/components/ui/overlay';
import { api, ApiError, messageOf } from '@/lib/api';
import { formatDateTime, plural } from '@/lib/format';
import { useTitle } from '@/lib/title';
import type { Page } from '@/lib/types';

type EvalSet = { id: number; name: string; description: string; cases: number };
type EvalCase = {
  id: number;
  set_id: number;
  query: string;
  relevant_job_ids: number[];
  notes: string;
};
type Metrics = Record<string, number>;
type ConfigResult = { name: string; cases: number; overall: Metrics };
type Run = {
  id: number;
  set_id: number | null;
  kind: string;
  status: 'queued' | 'running' | 'done' | 'failed';
  metrics: {
    configs?: ConfigResult[];
    skipped?: number;
    message?: string;
    tool_cases?: number;
    args_right?: number;
    refusal_cases?: number;
    refusals_passed?: number;
    ungrounded_shown?: number;
    turns?: number;
    structured?: number;
  };
  created_at: string;
};
type Rated = {
  id: number;
  rating: 'up' | 'down';
  comment: string;
  question: string;
  answer: string;
  cited_job_ids: number[];
  promoted: boolean;
  created_at: string;
};

const columns: [string, string][] = [
  ['hit@1', 'hit@1'],
  ['hit@3', 'hit@3'],
  ['hit@5', 'hit@5'],
  ['mrr', 'MRR'],
  ['ndcg@10', 'nDCG@10'],
  ['recall@50', 'recall@50'],
];

const kindText: Record<string, string> = {
  retrieval: 'Retrieval',
  'agent-mock': 'Copilot, mock mode',
  'agent-live': 'Copilot, live model',
};

function MetricsTable({ configs }: { configs: ConfigResult[] }) {
  const best = Object.fromEntries(
    columns.map(([key]) => [key, Math.max(...configs.map((c) => c.overall[key] ?? 0))]),
  );
  return (
    <div className="overflow-x-auto">
      <table className="mt-3 w-full text-sm">
        <caption className="sr-only">Retrieval metrics by configuration</caption>
        <thead>
          <tr className="text-muted-foreground border-b text-left">
            <th scope="col" className="py-2 pr-4 font-medium">
              Configuration
            </th>
            {columns.map(([key, label]) => (
              <th key={key} scope="col" className="py-2 pl-4 text-right font-medium">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular">
          {configs.map((config) => (
            <tr key={config.name} className="border-b last:border-0">
              <th scope="row" className="py-2 pr-4 text-left font-normal">
                {config.name}
              </th>
              {columns.map(([key]) => {
                const value = config.overall[key] ?? 0;
                return (
                  <td key={key} className="py-2 pl-4 text-right">
                    {value === best[key] ? (
                      <strong>
                        {value.toFixed(3)}
                        <span className="sr-only"> (best)</span>
                      </strong>
                    ) : (
                      value.toFixed(3)
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RunCard({ run, sets }: { run: Run; sets: EvalSet[] }) {
  const { metrics } = run;
  const name = sets.find((s) => s.id === run.set_id)?.name ?? 'Synthetic corpus (command line)';
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-medium">
          {kindText[run.kind] ?? run.kind} · {name}
        </h2>
        <span className="text-muted-foreground text-sm">{formatDateTime(run.created_at)}</span>
      </div>
      {(run.status === 'queued' || run.status === 'running') && (
        <div className="mt-3" role="status">
          <Progress value={50} label="Eval running" />
          <p className="text-muted-foreground mt-2 text-sm">Running. This takes a few seconds.</p>
        </div>
      )}
      {run.status === 'failed' && (
        <Alert tone="warning" className="mt-3">
          {metrics.message ?? 'The run did not finish. Start it again.'}
        </Alert>
      )}
      {metrics.configs && <MetricsTable configs={metrics.configs} />}
      {!!metrics.skipped && (
        <p className="text-muted-foreground mt-2 text-sm">
          {plural(metrics.skipped, 'case')} skipped because the relevant postings are closed.
        </p>
      )}
      {metrics.tool_cases !== undefined && run.status === 'done' && (
        <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-4">
          {[
            ['Right tool and arguments', `${metrics.args_right} of ${metrics.tool_cases}`],
            ['Honest refusals', `${metrics.refusals_passed} of ${metrics.refusal_cases}`],
            ['Ungrounded answers shown', `${metrics.ungrounded_shown} of ${metrics.turns}`],
            ['Valid structured output', `${metrics.structured} of ${metrics.turns}`],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="font-medium">{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  );
}

function CaseDialog({
  setId,
  editing,
  onClose,
}: {
  setId: number;
  editing: EvalCase | 'new';
  onClose: () => void;
}) {
  const client = useQueryClient();
  const initial = editing === 'new' ? null : editing;
  const [query, setQuery] = useState(initial?.query ?? '');
  const [ids, setIds] = useState((initial?.relevant_job_ids ?? []).map(String));
  const [notes, setNotes] = useState(initial?.notes ?? '');
  const save = useMutation({
    mutationFn: () => {
      const body = { query, notes, relevant_job_ids: ids.map(Number) };
      return initial
        ? api(`/admin/evals/cases/${initial.id}`, { method: 'PUT', body })
        : api(`/admin/evals/sets/${setId}/cases`, { method: 'POST', body });
    },
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['eval-cases'] });
      client.invalidateQueries({ queryKey: ['eval-sets'] });
      toast.success('Case saved');
      onClose();
    },
  });
  const error = save.error instanceof ApiError ? save.error : null;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={initial ? 'Edit case' : 'New case'}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        {save.isError && <Alert tone="danger">{messageOf(save.error)}</Alert>}
        <Field label="Query">
          {(p) => (
            <Input
              {...p}
              required
              minLength={2}
              maxLength={300}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          )}
        </Field>
        <Field
          label="Relevant postings"
          hint="Posting numbers, such as 12. Press Enter after each."
          error={error?.fieldError('relevant_job_ids')}
        >
          {(p) => (
            <TagInput
              {...p}
              itemName="posting number"
              values={ids}
              onChange={(v) =>
                setIds(v.map((x) => x.replace('#', '')).filter((x) => /^\d+$/.test(x)))
              }
            />
          )}
        </Field>
        <Field label="Notes">
          {(p) => (
            <Textarea
              {...p}
              maxLength={500}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          )}
        </Field>
        <Button type="submit" className="self-end" loading={save.isPending}>
          Save case
        </Button>
      </form>
    </Dialog>
  );
}

function CasesTab({ sets }: { sets: EvalSet[] }) {
  const client = useQueryClient();
  const [setId, setSetId] = useState(sets[0]?.id ?? 0);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<EvalCase | 'new' | null>(null);
  const [deleting, setDeleting] = useState<EvalCase | null>(null);
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState('');
  const query = useQuery({
    queryKey: ['eval-cases', setId, page],
    queryFn: () => api<Page<EvalCase>>(`/admin/evals/sets/${setId}/cases?page=${page}`),
    enabled: setId > 0,
    placeholderData: keepPreviousData,
  });
  const create = useMutation({
    mutationFn: () => api<{ id: number }>('/admin/evals/sets', { method: 'POST', body: { name } }),
    onSuccess: ({ id }) => {
      client.invalidateQueries({ queryKey: ['eval-sets'] });
      setSetId(id);
      setNaming(false);
      setName('');
    },
    onError: (error) => toast.error(messageOf(error)),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api<void>(`/admin/evals/cases/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Case deleted');
      client.invalidateQueries({ queryKey: ['eval-cases'] });
      client.invalidateQueries({ queryKey: ['eval-sets'] });
    },
    onError: (error) => toast.error(messageOf(error)),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        {sets.length > 0 && (
          <Field label="Set" className="w-72">
            {(ids) => (
              <Select
                {...ids}
                value={String(setId)}
                onValueChange={(v) => {
                  setSetId(Number(v));
                  setPage(1);
                }}
                options={sets.map((s) => ({
                  value: String(s.id),
                  label: `${s.name} (${s.cases})`,
                }))}
              />
            )}
          </Field>
        )}
        <Button variant="secondary" onClick={() => setNaming(true)}>
          New set
        </Button>
        {setId > 0 && (
          <Button onClick={() => setEditing('new')}>
            <Plus aria-hidden />
            Add case
          </Button>
        )}
      </div>
      {setId > 0 && (
        <QueryState query={query}>
          {(data) =>
            data.items.length ? (
              <>
                <Card>
                  <ul className="divide-y">
                    {data.items.map((item) => (
                      <li key={item.id} className="flex items-start gap-3 p-4">
                        <div className="min-w-0 flex-1 text-sm">
                          <p className="font-medium">{item.query}</p>
                          <p className="text-muted-foreground mt-1 flex flex-wrap gap-x-2">
                            {item.notes && <Badge>{item.notes}</Badge>}
                            {item.relevant_job_ids.length
                              ? item.relevant_job_ids.slice(0, 12).map((id) => (
                                  <Link
                                    key={id}
                                    to={`/admin/postings/${id}`}
                                    className="underline-offset-4 hover:underline"
                                  >
                                    #{id}
                                  </Link>
                                ))
                              : 'No relevant postings yet, so this case is skipped'}
                            {item.relevant_job_ids.length > 12 &&
                              `and ${item.relevant_job_ids.length - 12} more`}
                          </p>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Edit case: ${item.query}`}
                          onClick={() => setEditing(item)}
                        >
                          <Pencil aria-hidden />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Delete case: ${item.query}`}
                          onClick={() => setDeleting(item)}
                        >
                          <Trash2 aria-hidden />
                        </Button>
                      </li>
                    ))}
                  </ul>
                </Card>
                <Pagination
                  page={data.page}
                  pageSize={data.page_size}
                  total={data.total}
                  onChange={setPage}
                />
              </>
            ) : (
              <EmptyState icon={FlaskConical} title="No cases in this set">
                Add a query and the postings that should be found for it.
              </EmptyState>
            )
          }
        </QueryState>
      )}
      {editing && (
        <CaseDialog
          key={editing === 'new' ? 'new' : editing.id}
          setId={setId}
          editing={editing}
          onClose={() => setEditing(null)}
        />
      )}
      <Dialog open={naming} onOpenChange={setNaming} title="New eval set">
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <Field label="Name">
            {(ids) => (
              <Input
                {...ids}
                required
                minLength={3}
                maxLength={80}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            )}
          </Field>
          <Button type="submit" className="self-end" loading={create.isPending}>
            Create set
          </Button>
        </form>
      </Dialog>
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="Delete this case?"
        description={deleting?.query}
        confirmLabel="Delete"
        destructive
        onConfirm={() => deleting && remove.mutate(deleting.id)}
      />
    </div>
  );
}

function RunsTab({ sets }: { sets: EvalSet[] }) {
  const client = useQueryClient();
  const [setId, setSetId] = useState(sets[0]?.id ?? 0);
  const runs = useQuery({
    queryKey: ['eval-runs'],
    queryFn: () => api<Run[]>('/admin/evals/runs'),
    refetchInterval: (q) =>
      q.state.data?.some((r) => r.status === 'queued' || r.status === 'running') ? 1500 : false,
  });
  const start = useMutation({
    mutationFn: () => api<Run>(`/admin/evals/sets/${setId}/run`, { method: 'POST' }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['eval-runs'] }),
    onError: (error) => toast.error(messageOf(error)),
  });
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        {sets.length > 0 && (
          <Field label="Set" className="w-72">
            {(ids) => (
              <Select
                {...ids}
                value={String(setId)}
                onValueChange={(v) => setSetId(Number(v))}
                options={sets.map((s) => ({ value: String(s.id), label: s.name }))}
              />
            )}
          </Field>
        )}
        <Button
          onClick={() => start.mutate()}
          loading={start.isPending}
          disabled={!setId}
          title={setId ? undefined : 'Create a set first'}
        >
          <Play aria-hidden />
          Run retrieval eval
        </Button>
        <p className="text-muted-foreground text-sm">Free. No LLM calls.</p>
      </div>
      <QueryState query={runs}>
        {(items) =>
          items.length ? (
            <div className="flex flex-col gap-4">
              {items.map((run) => (
                <RunCard key={run.id} run={run} sets={sets} />
              ))}
            </div>
          ) : (
            <EmptyState icon={FlaskConical} title="No runs yet">
              Start one to compare semantic, keyword and hybrid search on your postings.
            </EmptyState>
          )
        }
      </QueryState>
    </div>
  );
}

function FeedbackTab() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ['eval-feedback'],
    queryFn: () => api<Rated[]>('/admin/evals/feedback'),
  });
  const promote = useMutation({
    mutationFn: (id: number) => api(`/admin/evals/feedback/${id}/promote`, { method: 'POST' }),
    onSuccess: () => {
      toast.success('Added to the “Student feedback” set');
      client.invalidateQueries({ queryKey: ['eval-feedback'] });
      client.invalidateQueries({ queryKey: ['eval-sets'] });
    },
    onError: (error) => toast.error(messageOf(error)),
  });
  return (
    <QueryState query={query}>
      {(items) =>
        items.length ? (
          <ul className="flex flex-col gap-4">
            {items.map((item) => (
              <li key={item.id}>
                <Card className="p-4 text-sm">
                  <div className="flex items-start gap-3">
                    {item.rating === 'up' ? (
                      <ThumbsUp className="text-success mt-0.5 size-4" aria-label="Rated good" />
                    ) : (
                      <ThumbsDown className="text-danger mt-0.5 size-4" aria-label="Rated poor" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{item.question || 'Question not stored'}</p>
                      <p className="text-muted-foreground mt-1 line-clamp-3 break-words whitespace-pre-line">
                        {item.answer}
                      </p>
                      {item.comment && <p className="mt-2">Comment: {item.comment}</p>}
                    </div>
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={item.promoted}
                      title={item.promoted ? 'Already an eval case' : undefined}
                      onClick={() => promote.mutate(item.id)}
                    >
                      {item.promoted ? 'Added' : 'Add as eval case'}
                    </Button>
                  </div>
                </Card>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState icon={ThumbsUp} title="No rated answers yet">
            When students rate a copilot answer, it appears here without their name.
          </EmptyState>
        )
      }
    </QueryState>
  );
}

export function EvalsPage() {
  useTitle('Evals');
  const [params, setParams] = useSearchParams();
  const sets = useQuery({
    queryKey: ['eval-sets'],
    queryFn: () => api<EvalSet[]>('/admin/evals/sets'),
  });
  return (
    <>
      <PageHeader
        title="Evals"
        description="Measure search quality on known answers, and turn student feedback into new cases."
      />
      <Tabs
        value={params.get('tab') ?? 'runs'}
        onValueChange={(tab) => setParams({ tab }, { replace: true })}
      >
        <TabsList aria-label="Sections">
          <TabsTrigger value="runs">Runs</TabsTrigger>
          <TabsTrigger value="cases">Cases</TabsTrigger>
          <TabsTrigger value="feedback">Student feedback</TabsTrigger>
        </TabsList>
        <QueryState query={sets}>
          {(items) => (
            <>
              <TabsContent value="runs" className="mt-4">
                <RunsTab sets={items} />
              </TabsContent>
              <TabsContent value="cases" className="mt-4">
                <CasesTab sets={items} />
              </TabsContent>
            </>
          )}
        </QueryState>
        <TabsContent value="feedback" className="mt-4">
          <FeedbackTab />
        </TabsContent>
      </Tabs>
    </>
  );
}
