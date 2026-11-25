import { useQuery } from '@tanstack/react-query';
import { StatTile } from '@/components/BarList';
import { QueryState } from '@/components/QueryState';
import { Alert, Badge, Card, PageHeader, Progress } from '@/components/ui/display';
import { api } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { useTitle } from '@/lib/title';

type Summary = {
  calls: number;
  live_calls: number;
  cache_hits: number;
  cache_hit_rate: number | null;
  input_tokens: number;
  output_tokens: number;
};
type Usage = {
  mode: 'mock' | 'live';
  model: string;
  budget: {
    live_today: number;
    live_total: number;
    daily_cap: number;
    total_cap: number;
    remaining_today: number;
  };
  today: Summary;
  all_time: Summary;
  by_purpose: {
    purpose: string;
    calls: number;
    live_calls: number;
    cache_hits: number;
    tokens: number;
    avg_latency_ms: number;
  }[];
  recent: {
    id: number;
    purpose: string;
    status: string;
    is_live: boolean;
    cache_hit: boolean;
    latency_ms: number;
    created_at: string;
  }[];
};

const purposeText: Record<string, string> = {
  parse_job: 'Reading postings',
  parse_resume: 'Reading resumes',
  agent_turn: 'Copilot chat',
  extract_memory: 'Memory suggestions',
  judge: 'Eval judge',
};

const statusText = (status: string) =>
  status === 'ok'
    ? 'Answered'
    : status === 'reserved'
      ? 'In progress'
      : status === 'http_429'
        ? 'Rate limited'
        : status.startsWith('network')
          ? 'Network problem'
          : 'Not answered';

export function UsagePage() {
  useTitle('LLM usage');
  const query = useQuery({
    queryKey: ['llm-usage'],
    queryFn: () => api<Usage>('/admin/llm-usage'),
    refetchInterval: 15_000,
  });
  return (
    <>
      <PageHeader
        title="LLM usage"
        description="Live calls cost budget. Cached answers and mock answers do not."
      />
      <QueryState query={query}>
        {(u) => (
          <div className="flex flex-col gap-6">
            {u.mode === 'mock' && (
              <Alert tone="info" title="Mock mode is on">
                No live calls are made. Answers come from built-in rules over the real postings.
              </Alert>
            )}
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <StatTile label="Live calls today" value={u.budget.live_today} />
              <StatTile
                label="All calls today"
                value={u.today.calls}
                hint="Live, cached and mock"
              />
              <StatTile
                label="Cache hit rate"
                value={
                  u.all_time.cache_hit_rate === null
                    ? '–'
                    : `${Math.round(u.all_time.cache_hit_rate * 100)}%`
                }
                hint={
                  u.all_time.cache_hit_rate === null
                    ? 'No live or cached calls yet'
                    : `${u.all_time.cache_hits} answers reused`
                }
              />
              <StatTile
                label="Live calls in total"
                value={u.budget.live_total}
                hint={`Cap ${u.budget.total_cap}`}
              />
            </div>
            <Card className="p-5">
              <div className="flex justify-between gap-4">
                <h2 className="font-semibold">Budget left today</h2>
                <span className="tabular text-sm">
                  {u.budget.remaining_today} of {u.budget.daily_cap}
                </span>
              </div>
              <div className="mt-3">
                <Progress
                  value={(u.budget.remaining_today / Math.max(1, u.budget.daily_cap)) * 100}
                  label="Budget left today"
                />
              </div>
            </Card>
            <Card className="overflow-x-auto p-5">
              <h2 className="font-semibold">By purpose</h2>
              {u.by_purpose.length === 0 ? (
                <p className="text-muted-foreground mt-2 text-sm">No calls yet.</p>
              ) : (
                <table className="mt-3 w-full text-sm">
                  <thead>
                    <tr className="text-muted-foreground border-b text-left">
                      <th className="py-2 pr-4 font-medium">Purpose</th>
                      <th className="py-2 pr-4 text-right font-medium">Calls</th>
                      <th className="py-2 pr-4 text-right font-medium">Live</th>
                      <th className="py-2 pr-4 text-right font-medium">Cached</th>
                      <th className="py-2 pr-4 text-right font-medium">Tokens</th>
                      <th className="py-2 text-right font-medium">Average time</th>
                    </tr>
                  </thead>
                  <tbody className="tabular">
                    {u.by_purpose.map((p) => (
                      <tr key={p.purpose} className="border-b last:border-0">
                        <th scope="row" className="py-2 pr-4 text-left font-normal">
                          {purposeText[p.purpose] ?? p.purpose}
                        </th>
                        <td className="py-2 pr-4 text-right">{p.calls}</td>
                        <td className="py-2 pr-4 text-right">{p.live_calls}</td>
                        <td className="py-2 pr-4 text-right">{p.cache_hits}</td>
                        <td className="py-2 pr-4 text-right">{p.tokens.toLocaleString('en-IN')}</td>
                        <td className="py-2 text-right">{p.avg_latency_ms} ms</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
            <Card className="overflow-x-auto p-5">
              <h2 className="font-semibold">Latest calls</h2>
              <ul className="mt-3 divide-y text-sm">
                {u.recent.map((call) => (
                  <li key={call.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2">
                    <span className="min-w-36">{purposeText[call.purpose] ?? call.purpose}</span>
                    <Badge tone={call.is_live ? 'accent' : call.cache_hit ? 'info' : 'neutral'}>
                      {call.is_live ? 'Live' : call.cache_hit ? 'Cached' : 'Mock'}
                    </Badge>
                    <span>{statusText(call.status)}</span>
                    <span className="text-muted-foreground ml-auto">
                      {formatDateTime(call.created_at)}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        )}
      </QueryState>
    </>
  );
}
