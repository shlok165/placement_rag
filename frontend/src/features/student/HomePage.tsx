import { useQuery } from '@tanstack/react-query';
import { ClipboardList, Sparkles } from 'lucide-react';
import { Link } from 'react-router';
import { JobCard } from './JobCard';
import { QueryState } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { Alert, Card, EmptyState, PageHeader } from '@/components/ui/display';
import { api } from '@/lib/api';
import { useUser } from '@/lib/auth';
import { deadlineText, plural } from '@/lib/format';
import { stageLabel, stages } from '@/lib/stages';
import { useTitle } from '@/lib/title';
import type { Home } from '@/lib/types';

export function HomePage() {
  useTitle('Home');
  const { data: user } = useUser();
  const query = useQuery({ queryKey: ['home'], queryFn: () => api<Home>('/home') });
  const firstName = user?.full_name.split(' ')[0];

  return (
    <>
      <PageHeader
        title={firstName ? `Hello, ${firstName}` : 'Home'}
        actions={
          <Button asChild>
            <Link to="/jobs">Browse postings</Link>
          </Button>
        }
      />
      <QueryState query={query}>
        {(home) => (
          <div className="grid items-start gap-6 lg:grid-cols-[1fr_20rem]">
            <section aria-labelledby="recommended">
              <h2 id="recommended" className="text-lg font-semibold">
                Recommended for you
              </h2>
              <p className="text-muted-foreground mb-4 text-sm">
                {home.profile_ready
                  ? 'Ranked by your skills and preferences. Open one to see why.'
                  : 'Closing soonest first, until we know more about you.'}
              </p>
              {!home.profile_ready && (
                <Alert
                  tone="info"
                  title="Make this list yours"
                  className="mb-4"
                  action={
                    <Button asChild variant="secondary" size="sm">
                      <Link to="/onboarding">Add your profile</Link>
                    </Button>
                  }
                >
                  Add skills and preferences to get ranked recommendations.
                </Alert>
              )}
              {home.recommended.length ? (
                <ul className="flex flex-col gap-4">
                  {home.recommended.map((hit) => (
                    <li key={hit.job.id}>
                      <JobCard hit={hit} />
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState icon={Sparkles} title="No open postings right now">
                  New postings appear here as soon as the CAPS team publishes them.
                </EmptyState>
              )}
            </section>
            <aside aria-label="Your updates" className="flex flex-col gap-6">
              <Card className="p-5">
                <h2 className="font-semibold">Your applications</h2>
                {Object.keys(home.pipeline).length ? (
                  <>
                    <ul className="mt-3 flex flex-col gap-2 text-sm">
                      {stages
                        .filter((s) => home.pipeline[s])
                        .map((s) => (
                          <li key={s} className="flex justify-between">
                            <span>{stageLabel[s]}</span>
                            <span className="tabular font-medium">{home.pipeline[s]}</span>
                          </li>
                        ))}
                    </ul>
                    <Button asChild variant="secondary" size="sm" className="mt-4">
                      <Link to="/applications">Open tracker</Link>
                    </Button>
                  </>
                ) : (
                  <p className="text-muted-foreground mt-2 flex gap-2 text-sm">
                    <ClipboardList className="mt-0.5 size-4 shrink-0" aria-hidden />
                    Track an application from any posting and it shows up here.
                  </p>
                )}
              </Card>
              <Card className="p-5">
                <h2 className="font-semibold">Closing this week</h2>
                {home.closing_soon.length ? (
                  <ul className="mt-2 divide-y text-sm">
                    {home.closing_soon.map(({ job }) => (
                      <li key={job.id} className="py-2">
                        <Link
                          to={`/jobs/${job.id}`}
                          className="font-medium underline-offset-4 hover:underline"
                        >
                          {job.title}
                        </Link>
                        <p className="text-muted-foreground">
                          {job.company} · {deadlineText(job.deadline)}
                        </p>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted-foreground mt-2 text-sm">
                    Nothing closes in the next 7 days.
                  </p>
                )}
              </Card>
              {home.unread > 0 && (
                <Card className="p-5">
                  <h2 className="font-semibold">Notifications</h2>
                  <p className="text-muted-foreground mt-1 text-sm">
                    {plural(home.unread, 'unread update')}
                  </p>
                  <Button asChild variant="secondary" size="sm" className="mt-3">
                    <Link to="/notifications">Read them</Link>
                  </Button>
                </Card>
              )}
            </aside>
          </div>
        )}
      </QueryState>
    </>
  );
}
