import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { BarList, StatTile } from '@/components/BarList';
import { QueryState } from '@/components/QueryState';
import { statusLabel } from '@/components/StatusBadge';
import { Button } from '@/components/ui/button';
import { Alert, Card, PageHeader } from '@/components/ui/display';
import { api } from '@/lib/api';
import { stageLabel, stages } from '@/lib/stages';
import { deadlineText, plural } from '@/lib/format';
import { useTitle } from '@/lib/title';
import type { JobStatus } from '@/lib/types';

type Top = { id: number; title: string; company: string; count: number };
type Dashboard = {
  postings_by_status: Record<JobStatus, number>;
  needs_review: number;
  closing_soon: { id: number; title: string; company: string; deadline: string }[];
  content_gaps: { query: string; searches: number; best_results: number }[];
  most_viewed: Top[];
  most_saved: Top[];
  students_total: number;
  students_active: number;
  applications_by_stage: Record<string, number>;
};

function Panel({
  title,
  hint,
  empty,
  children,
}: {
  title: string;
  hint?: string;
  empty?: string | false;
  children: ReactNode;
}) {
  return (
    <Card className="mb-6 break-inside-avoid p-5">
      <h2 className="font-semibold">{title}</h2>
      {hint && <p className="text-muted-foreground text-sm">{hint}</p>}
      <div className="mt-3">
        {empty ? <p className="text-muted-foreground text-sm">{empty}</p> : children}
      </div>
    </Card>
  );
}

function JobLink({ job }: { job: { id: number; title: string; company: string } }) {
  return (
    <Link to={`/admin/postings/${job.id}`} className="underline-offset-4 hover:underline">
      {job.title} <span className="text-muted-foreground">· {job.company}</span>
    </Link>
  );
}

export function DashboardPage() {
  useTitle('Dashboard');
  const query = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => api<Dashboard>('/admin/dashboard'),
  });
  return (
    <>
      <PageHeader
        title="Dashboard"
        actions={
          <Button asChild>
            <Link to="/admin/postings/new">Add posting</Link>
          </Button>
        }
      />
      <QueryState query={query}>
        {(d) => {
          const tracked = stages.filter((s) => d.applications_by_stage[s]);
          return (
            <div className="flex flex-col gap-6">
              {d.postings_by_status.failed > 0 && (
                <Alert
                  tone="danger"
                  title={`${plural(d.postings_by_status.failed, 'posting')} could not be processed`}
                  action={
                    <Button variant="secondary" size="sm" asChild>
                      <Link to="/admin/postings?status=failed">Review failed</Link>
                    </Button>
                  }
                />
              )}
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <StatTile label="Live postings" value={d.postings_by_status.indexed} />
                <StatTile
                  label="Waiting for review"
                  value={d.needs_review}
                  hint={
                    d.needs_review > 0 ? (
                      <Link className="underline" to="/admin/postings?status=draft">
                        Open drafts
                      </Link>
                    ) : (
                      'Nothing to review'
                    )
                  }
                />
                <StatTile
                  label="Active students"
                  value={d.students_active}
                  hint={`of ${d.students_total}, in the last 14 days`}
                />
                <StatTile label="Closing in 7 days" value={d.closing_soon.length} />
              </div>
              <div className="gap-6 lg:columns-2">
                <Panel title="Postings by status">
                  <BarList
                    caption="Postings by status"
                    valueLabel="postings"
                    items={(Object.keys(d.postings_by_status) as JobStatus[]).map((s) => ({
                      key: s,
                      label: (
                        <Link
                          to={`/admin/postings?status=${s}`}
                          className="underline-offset-4 hover:underline"
                        >
                          {statusLabel(s)}
                        </Link>
                      ),
                      value: d.postings_by_status[s],
                    }))}
                  />
                </Panel>
                <Panel
                  title="Applications by stage"
                  hint="Counts only, across all students"
                  empty={tracked.length === 0 && 'No one is tracking an application yet.'}
                >
                  <BarList
                    caption="Applications by stage"
                    valueLabel="applications"
                    items={tracked.map((s) => ({
                      key: s,
                      label: stageLabel[s],
                      value: d.applications_by_stage[s],
                    }))}
                  />
                </Panel>
                <Panel
                  title="Searches with no good results"
                  hint="What students looked for and did not find in the last 30 days"
                  empty={d.content_gaps.length === 0 && 'No gaps so far. Good coverage.'}
                >
                  <BarList
                    caption="Searches with no good results"
                    valueLabel="searches"
                    items={d.content_gaps.map((g) => ({
                      key: g.query,
                      label: g.query,
                      value: g.searches,
                    }))}
                  />
                </Panel>
                <Panel
                  title="Closing soon"
                  empty={d.closing_soon.length === 0 && 'Nothing closes in the next 7 days.'}
                >
                  <ul className="divide-y text-sm">
                    {d.closing_soon.map((job) => (
                      <li key={job.id} className="flex justify-between gap-4 py-2">
                        <JobLink job={job} />
                        <span className="text-muted-foreground whitespace-nowrap">
                          {deadlineText(job.deadline)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </Panel>
                <Panel
                  title="Most viewed"
                  hint="Last 30 days"
                  empty={d.most_viewed.length === 0 && 'No views yet.'}
                >
                  <BarList
                    caption="Most viewed postings"
                    valueLabel="views"
                    items={d.most_viewed.map((job) => ({
                      key: String(job.id),
                      label: <JobLink job={job} />,
                      value: job.count,
                    }))}
                  />
                </Panel>
                <Panel title="Most saved" empty={d.most_saved.length === 0 && 'No saves yet.'}>
                  <BarList
                    caption="Most saved postings"
                    valueLabel="saves"
                    items={d.most_saved.map((job) => ({
                      key: String(job.id),
                      label: <JobLink job={job} />,
                      value: job.count,
                    }))}
                  />
                </Panel>
              </div>
            </div>
          );
        }}
      </QueryState>
    </>
  );
}
