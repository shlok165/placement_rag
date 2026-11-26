import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, SearchX, ThumbsDown, ThumbsUp } from 'lucide-react';
import { Link, useParams } from 'react-router';
import { toast } from 'sonner';
import { FitPanel } from './FitPanel';
import { useTrack } from './hooks';
import { DeadlineBadge, JobFacts, SaveButton } from './JobCard';
import { Breadcrumb } from '@/components/Breadcrumb';
import { QueryState } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { Alert, Badge, Card, EmptyState } from '@/components/ui/display';
import { Field, Select } from '@/components/ui/form';
import { api, ApiError, messageOf } from '@/lib/api';
import { recordEvent } from '@/lib/events';
import { deadlineText, formatDate } from '@/lib/format';
import { stageOptions, type Stage } from '@/lib/stages';
import { useTitle } from '@/lib/title';
import type { JobDetail } from '@/lib/types';

function Reaction({ jobId, value }: { jobId: number; value: JobDetail['reaction'] }) {
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: (reaction: JobDetail['reaction']) =>
      api<{ reaction: JobDetail['reaction'] }>(`/jobs/${jobId}/reaction`, {
        method: 'PUT',
        body: { reaction },
      }),
    onSuccess: ({ reaction }) => {
      client.setQueryData<JobDetail>(['job', jobId], (old) => (old ? { ...old, reaction } : old));
      client.invalidateQueries({ queryKey: ['home'] });
      toast.success(
        reaction === null
          ? 'Cleared'
          : reaction === 'up'
            ? 'You will see more postings like this'
            : 'You will see fewer postings like this',
      );
    },
    onError: (error) => toast.error(messageOf(error)),
  });
  const choose = (next: 'up' | 'down') => mutation.mutate(value === next ? null : next);
  return (
    <Card className="p-5">
      <h2 className="font-semibold">Your recommendations</h2>
      <p className="text-muted-foreground mt-1 text-sm">
        This changes only how postings are ordered for you. Press again to undo.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          variant="secondary"
          aria-pressed={value === 'up'}
          disabled={mutation.isPending}
          onClick={() => choose('up')}
          className="aria-pressed:border-primary aria-pressed:border"
        >
          <ThumbsUp aria-hidden />
          More like this
        </Button>
        <Button
          variant="secondary"
          aria-pressed={value === 'down'}
          disabled={mutation.isPending}
          onClick={() => choose('down')}
          className="aria-pressed:border-primary aria-pressed:border"
        >
          <ThumbsDown aria-hidden />
          Fewer like this
        </Button>
      </div>
    </Card>
  );
}

function Detail({ data }: { data: JobDetail }) {
  const { job, application } = data;
  const track = useTrack();
  const closed = job.status !== 'indexed' || deadlineText(job.deadline) === 'Closed';

  return (
    <>
      <Breadcrumb items={[['/jobs', 'Browse']]} current={job.title} />
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold">{job.title}</h1>
          <p className="mt-1">{job.company}</p>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
            <JobFacts job={job} />
            <DeadlineBadge deadline={job.deadline} />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <SaveButton jobId={job.id} title={job.title} saved={data.saved} label />
          {job.apply_url && !closed && (
            <Button asChild>
              <a
                href={job.apply_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => recordEvent(job.id, 'apply_clicked')}
              >
                Apply
                <ExternalLink aria-hidden />
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            </Button>
          )}
        </div>
      </header>
      {closed && (
        <Alert tone="warning" title="This posting is closed" className="mb-6">
          Applications are no longer open. Similar postings are listed below.
        </Alert>
      )}
      <div className="grid items-start gap-6 lg:grid-cols-[1fr_22rem]">
        <div className="flex flex-col gap-6">
          <Card className="p-5">
            <h2 className="font-semibold">About the role</h2>
            <p className="mt-2 max-w-prose whitespace-pre-line">{job.description}</p>
            {job.requirements && (
              <>
                <h2 className="mt-5 font-semibold">Requirements</h2>
                <p className="mt-2 max-w-prose whitespace-pre-line">{job.requirements}</p>
              </>
            )}
            {job.skills.length > 0 && (
              <>
                <h2 className="mt-5 font-semibold">Skills</h2>
                <ul className="mt-2 flex flex-wrap gap-2">
                  {job.skills.map((skill) => (
                    <li key={skill}>
                      <Badge>{skill}</Badge>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <p className="text-muted-foreground mt-5 text-sm">
              Apply by {formatDate(job.deadline)} · Posting #{job.id}
            </p>
          </Card>
          {data.similar.length > 0 && (
            <section aria-labelledby="similar">
              <h2 id="similar" className="mb-3 font-semibold">
                Similar postings
              </h2>
              <ul className="grid gap-3 sm:grid-cols-2">
                {data.similar.map((other) => (
                  <li key={other.id}>
                    <Card className="hover:border-input relative h-full p-4">
                      <Link
                        to={`/jobs/${other.id}`}
                        className="font-medium after:absolute after:inset-0"
                      >
                        {other.title}
                      </Link>
                      <p className="text-muted-foreground text-sm">
                        {other.company} · {deadlineText(other.deadline)}
                      </p>
                    </Card>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
        <aside aria-label="Tracking and fit" className="flex flex-col gap-6">
          <Card className="p-5">
            <h2 className="font-semibold">Track this application</h2>
            <div className="mt-3">
              {application ? (
                <>
                  <Field label="Stage">
                    {(ids) => (
                      <Select
                        {...ids}
                        value={application.status}
                        onValueChange={(value) =>
                          track({
                            jobId: job.id,
                            status: value as Stage,
                            previous: application.status,
                          })
                        }
                        options={stageOptions}
                      />
                    )}
                  </Field>
                  <Button asChild variant="link" className="mt-2 h-auto px-0">
                    <Link to="/applications">Add notes in the tracker</Link>
                  </Button>
                </>
              ) : (
                <>
                  <p className="text-muted-foreground mb-3 text-sm">
                    Keep stages and notes in one place. This does not submit an application.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="secondary"
                      onClick={() => track({ jobId: job.id, status: 'interested', previous: null })}
                    >
                      I am interested
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => track({ jobId: job.id, status: 'applied', previous: null })}
                    >
                      I have applied
                    </Button>
                  </div>
                </>
              )}
            </div>
          </Card>
          <FitPanel breakdown={data.breakdown} />
          <Reaction jobId={job.id} value={data.reaction ?? null} />
        </aside>
      </div>
    </>
  );
}

export function JobDetailPage() {
  const id = Number(useParams().id);
  const query = useQuery({
    queryKey: ['job', id],
    queryFn: () => api<JobDetail>(`/jobs/${id}`),
  });
  useTitle(query.data?.job.title ?? 'Posting');
  if (query.error instanceof ApiError && query.error.status === 404) {
    return (
      <>
        <h1 className="sr-only">Posting not available</h1>
        <EmptyState
          icon={SearchX}
          title="That posting is not available"
          action={
            <Button asChild>
              <Link to="/jobs">Browse open postings</Link>
            </Button>
          }
        >
          It may have been removed by the CAPS team.
        </EmptyState>
      </>
    );
  }
  return <QueryState query={query}>{(data) => <Detail data={data} />}</QueryState>;
}
