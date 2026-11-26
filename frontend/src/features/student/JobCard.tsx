import { Bookmark, BookmarkCheck, Check, Clock, MapPin, Wallet } from 'lucide-react';
import { Link } from 'react-router';
import { useSaveJob } from './hooks';
import { Button } from '@/components/ui/button';
import { Badge, Card } from '@/components/ui/display';
import { Tooltip } from '@/components/ui/overlay';
import { useImpressions } from '@/lib/events';
import { daysUntil, deadlineText, payText, placeText, typeText } from '@/lib/format';
import { stageLabel, type Stage } from '@/lib/stages';
import type { Breakdown, Job, SearchHit } from '@/lib/types';

export function DeadlineBadge({ deadline }: { deadline: string | null }) {
  const days = daysUntil(deadline);
  const tone = days === null ? 'neutral' : days < 0 ? 'danger' : days <= 3 ? 'warning' : 'neutral';
  return (
    <Badge tone={tone}>
      <Clock aria-hidden />
      {deadlineText(deadline)}
    </Badge>
  );
}

export function JobFacts({ job }: { job: Job }) {
  const pay = payText(job);
  return (
    <ul className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-sm">
      <li className="flex items-center gap-1.5">
        <MapPin className="size-4" aria-hidden />
        {placeText(job)}
      </li>
      <li>{typeText(job.job_type)}</li>
      {job.duration_months && <li>{job.duration_months} months</li>}
      {pay && (
        <li className="flex items-center gap-1.5">
          <Wallet className="size-4" aria-hidden />
          {pay}
        </li>
      )}
    </ul>
  );
}

export function MatchBadge({ breakdown }: { breakdown: Breakdown | null }) {
  if (!breakdown || breakdown.match_percent === null) return null;
  const percent = breakdown.match_percent;
  return (
    <Tooltip content="How well this fits your skills and preferences. Open the posting to see why.">
      <Badge tone={percent >= 60 ? 'accent' : 'neutral'} tabIndex={0}>
        {percent}% match
      </Badge>
    </Tooltip>
  );
}

export function SkillChips({ breakdown, limit = 6 }: { breakdown: Breakdown; limit?: number }) {
  const all = [
    ...breakdown.matched_skills.map((name) => ({ name, has: true })),
    ...breakdown.missing_skills.map((name) => ({ name, has: false })),
  ];
  const rest = all.length - limit;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Skills">
      {all.slice(0, limit).map(({ name, has }) => (
        <li key={name}>
          <Badge tone={has ? 'success' : 'outline'}>
            {has && <Check aria-hidden />}
            {name}
            <span className="sr-only">{has ? ', you have this' : ', not in your profile'}</span>
          </Badge>
        </li>
      ))}
      {rest > 0 && (
        <li>
          <Badge tone="outline">+{rest} more</Badge>
        </li>
      )}
    </ul>
  );
}

export function SaveButton({
  jobId,
  title,
  saved,
  label = false,
}: {
  jobId: number;
  title: string;
  saved: boolean;
  label?: boolean;
}) {
  const save = useSaveJob();
  const Icon = saved ? BookmarkCheck : Bookmark;
  return (
    <Button
      variant={label ? 'secondary' : 'ghost'}
      size={label ? 'md' : 'icon'}
      aria-pressed={saved}
      aria-label={label ? undefined : `${saved ? 'Remove from saved' : 'Save'}: ${title}`}
      onClick={() => save(jobId, !saved)}
    >
      <Icon className={saved ? 'text-primary' : undefined} aria-hidden />
      {label && (saved ? 'Saved' : 'Save')}
    </Button>
  );
}

export function JobCard({ hit, level: Heading = 'h3' }: { hit: SearchHit; level?: 'h2' | 'h3' }) {
  const { job, breakdown } = hit;
  useImpressions([job.id]);
  return (
    <Card className="hover:border-input relative p-4 transition-colors sm:p-5">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <Heading className="font-semibold">
            <Link
              to={`/jobs/${job.id}`}
              className="underline-offset-4 after:absolute after:inset-0 after:rounded-lg hover:underline"
            >
              {job.title}
            </Link>
          </Heading>
          <p className="text-sm">{job.company}</p>
        </div>
        <div className="relative z-10 -mt-1 -mr-1 flex items-center gap-1">
          <SaveButton jobId={job.id} title={job.title} saved={hit.saved} />
        </div>
      </div>
      <div className="mt-2">
        <JobFacts job={job} />
      </div>
      {breakdown && breakdown.matched_skills.length + breakdown.missing_skills.length > 0 ? (
        <div className="mt-3">
          <SkillChips breakdown={breakdown} />
        </div>
      ) : (
        job.skills.length > 0 && (
          <p className="text-muted-foreground mt-3 text-sm">{job.skills.slice(0, 6).join(', ')}</p>
        )
      )}
      <div className="relative z-10 mt-3 flex w-fit flex-wrap gap-2">
        <MatchBadge breakdown={breakdown} />
        <DeadlineBadge deadline={job.deadline} />
        {hit.application_status && (
          <Badge tone="info">{stageLabel[hit.application_status as Stage]}</Badge>
        )}
      </div>
    </Card>
  );
}
