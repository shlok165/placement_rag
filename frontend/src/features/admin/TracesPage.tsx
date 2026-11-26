import { useQuery } from '@tanstack/react-query';
import { Check, Route as RouteIcon, X } from 'lucide-react';
import { Link, useParams } from 'react-router';
import { Breadcrumb } from '@/components/Breadcrumb';
import { QueryState } from '@/components/QueryState';
import { Alert, Badge, Card, EmptyState, PageHeader } from '@/components/ui/display';
import { api } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { useTitle } from '@/lib/title';

type TraceRow = {
  message_id: number;
  created_at: string;
  source: 'own' | 'shared';
  rating: 'up' | 'down' | null;
  question: string;
  answer_kind: string | null;
  tools: number;
  latency_ms: number | null;
};

type ToolStep = {
  name: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  summary: string;
  ms?: number;
};

type Trace = {
  message_id: number;
  created_at: string;
  source: 'own' | 'shared';
  rating: 'up' | 'down' | null;
  comment: string;
  question: string;
  answer: string;
  citations: { job_id: number; title: string; company: string }[];
  tools: ToolStep[];
  checks: {
    answer_kind: string | null;
    structured: boolean | null;
    format_repairs: number;
    fabrications_caught: number;
    notice: string | null;
    draft: boolean;
  };
  mode: string | null;
  iterations: number | null;
  tokens: number | null;
  latency_ms: number | null;
  cache_hits: number;
};

const kindText: Record<string, string> = {
  structured: 'Structured at the first attempt',
  repaired: 'Structured after a repair',
  fallback: 'Built by code',
};

export function TracesPage() {
  useTitle('Agent traces');
  const query = useQuery({ queryKey: ['traces'], queryFn: () => api<TraceRow[]>('/admin/traces') });
  return (
    <>
      <PageHeader
        title="Agent traces"
        description="The steps behind copilot answers: your own, and those students rated and chose to share."
      />
      <QueryState query={query}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState icon={RouteIcon} title="No traces to show yet">
              A trace appears here when a student rates an answer and agrees to share its steps.
            </EmptyState>
          ) : (
            <Card className="overflow-x-auto" role="region" aria-label="Traces" tabIndex={0}>
              <table className="w-full text-sm">
                <thead className="text-muted-foreground text-left">
                  <tr>
                    <th scope="col" className="p-3 font-medium">
                      Question
                    </th>
                    <th scope="col" className="p-3 font-medium">
                      From
                    </th>
                    <th scope="col" className="p-3 font-medium">
                      Answer
                    </th>
                    <th scope="col" className="p-3 text-right font-medium">
                      Tools
                    </th>
                    <th scope="col" className="p-3 text-right font-medium">
                      Time
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.message_id} className="border-t">
                      <td className="max-w-md p-3">
                        <Link
                          className="font-medium underline-offset-4 hover:underline"
                          to={`/admin/traces/${row.message_id}`}
                        >
                          {row.question || '(no question)'}
                        </Link>
                        <div className="text-muted-foreground text-xs">
                          {formatDateTime(row.created_at)}
                        </div>
                      </td>
                      <td className="p-3">
                        {row.source === 'own' ? 'You' : 'A student'}
                        {row.rating && (
                          <span className="text-muted-foreground">
                            {' '}
                            · rated {row.rating === 'up' ? 'good' : 'poor'}
                          </span>
                        )}
                      </td>
                      <td className="p-3">{kindText[row.answer_kind ?? ''] ?? 'Unknown'}</td>
                      <td className="tabular p-3 text-right">{row.tools}</td>
                      <td className="tabular p-3 text-right">
                        {row.latency_ms === null ? '–' : `${(row.latency_ms / 1000).toFixed(1)} s`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )
        }
      </QueryState>
    </>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="tabular font-medium">{value}</dd>
    </div>
  );
}

export function TraceDetailPage() {
  const id = Number(useParams().id);
  const query = useQuery({
    queryKey: ['trace', id],
    queryFn: () => api<Trace>(`/admin/traces/${id}`),
  });
  useTitle('Trace');
  return (
    <QueryState query={query}>
      {(trace) => (
        <>
          <Breadcrumb
            items={[['/admin/traces', 'Agent traces']]}
            current={`Answer #${trace.message_id}`}
          />
          <PageHeader title={trace.question || 'Copilot answer'} />
          {trace.source === 'shared' && (
            <Alert className="mb-6" title="Shared by a student">
              The student agreed to share these steps. This view is recorded in the change history.
              {trace.comment && <> Their comment: “{trace.comment}”</>}
            </Alert>
          )}
          <div className="grid items-start gap-6 lg:grid-cols-[1fr_20rem]">
            <div className="flex flex-col gap-6">
              <Card className="p-5">
                <h2 className="font-semibold">Steps</h2>
                {trace.tools.length === 0 ? (
                  <p className="text-muted-foreground mt-2 text-sm">No tool was called.</p>
                ) : (
                  <ol className="mt-3 flex flex-col gap-3">
                    {trace.tools.map((step, index) => (
                      <li key={index} className="rounded-md border p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          {step.ok ? (
                            <Check className="text-success size-4" aria-hidden />
                          ) : (
                            <X className="text-danger size-4" aria-hidden />
                          )}
                          <span className="font-mono text-sm font-medium">{step.name}</span>
                          <span className="sr-only">{step.ok ? 'succeeded' : 'failed'}</span>
                          {step.ms !== undefined && <Badge>{step.ms} ms</Badge>}
                        </div>
                        <pre className="bg-muted mt-2 overflow-x-auto rounded p-2 text-xs">
                          {JSON.stringify(step.arguments, null, 2)}
                        </pre>
                        {step.summary && (
                          <p className="text-muted-foreground mt-1 text-sm">{step.summary}</p>
                        )}
                      </li>
                    ))}
                  </ol>
                )}
              </Card>
              <Card className="p-5">
                <h2 className="font-semibold">Answer shown</h2>
                <p className="mt-2 max-w-prose text-sm whitespace-pre-line">{trace.answer}</p>
                {trace.citations.length > 0 && (
                  <p className="text-muted-foreground mt-3 text-sm">
                    Cites {trace.citations.map((c) => `#${c.job_id}`).join(', ')}
                  </p>
                )}
              </Card>
            </div>
            <Card className="p-5">
              <h2 className="font-semibold">Checks and cost</h2>
              <dl className="mt-3 grid grid-cols-2 gap-3">
                <Fact
                  label="Answer"
                  value={kindText[trace.checks.answer_kind ?? ''] ?? 'Unknown'}
                />
                <Fact label="Grounding" value="Passed" />
                <Fact label="Format repairs" value={String(trace.checks.format_repairs)} />
                <Fact label="Drafts stopped" value={String(trace.checks.fabrications_caught)} />
                <Fact label="Model calls" value={String(trace.iterations ?? '–')} />
                <Fact label="From cache" value={String(trace.cache_hits)} />
                <Fact label="Tokens" value={(trace.tokens ?? 0).toLocaleString('en-IN')} />
                <Fact
                  label="Time"
                  value={
                    trace.latency_ms === null ? '–' : `${(trace.latency_ms / 1000).toFixed(1)} s`
                  }
                />
                <Fact label="Mode" value={trace.mode ?? '–'} />
                <Fact label="Draft shown" value={trace.checks.draft ? 'Yes' : 'No'} />
              </dl>
              {trace.checks.notice && (
                <p className="text-muted-foreground mt-3 text-sm">{trace.checks.notice}</p>
              )}
              <p className="text-muted-foreground mt-3 text-xs">
                Every shown answer passed the grounding check: a failing one is never displayed.
              </p>
            </Card>
          </div>
        </>
      )}
    </QueryState>
  );
}
