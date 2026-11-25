import { Check, X } from 'lucide-react';
import { Link } from 'react-router';
import { SkillChips } from './JobCard';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/display';
import type { Breakdown } from '@/lib/types';

export function FitPanel({ breakdown }: { breakdown: Breakdown | null }) {
  if (!breakdown || breakdown.match_percent === null) {
    return (
      <Card className="p-5">
        <h2 className="font-semibold">Why this fits</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          Add your skills and preferences to see how well this posting fits you.
        </p>
        <Button asChild variant="secondary" className="mt-3">
          <Link to="/account">Complete your profile</Link>
        </Button>
      </Card>
    );
  }
  const parts = breakdown.components.filter((c) => c.key !== 'urgency');
  return (
    <Card className="p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-semibold">Why this fits</h2>
        <p className="text-sm">
          <span className="text-lg font-semibold">{breakdown.match_percent}%</span> match
        </p>
      </div>
      <p className="text-muted-foreground mt-1 text-sm">
        Worked out from your profile with a fixed formula. It compares fit only and does not predict
        selection.
      </p>
      <dl className="mt-4 flex flex-col gap-3">
        {parts.map((part) => (
          <div key={part.key}>
            <div className="flex justify-between gap-3 text-sm">
              <dt className="font-medium">{part.label}</dt>
              <dd className="tabular">
                {part.value === null ? 'Not counted' : `${Math.round(part.value * 100)}%`}
              </dd>
            </div>
            <div className="bg-secondary mt-1 h-1.5 overflow-hidden rounded-full" aria-hidden>
              <div
                className="bg-primary h-full rounded-full"
                style={{ width: `${(part.value ?? 0) * 100}%` }}
              />
            </div>
            <p className="text-muted-foreground mt-1 text-xs">
              {part.note}. Weight {part.weight.toFixed(2)}.
            </p>
          </div>
        ))}
      </dl>
      {breakdown.preference_checks.length > 0 && (
        <>
          <h3 className="mt-5 text-sm font-medium">Your preferences</h3>
          <ul className="mt-2 flex flex-col gap-1.5 text-sm">
            {breakdown.preference_checks.map((check) => (
              <li key={check.key} className="flex items-start gap-2">
                {check.met ? (
                  <Check className="text-success mt-0.5 size-4 shrink-0" aria-hidden />
                ) : (
                  <X className="text-danger mt-0.5 size-4 shrink-0" aria-hidden />
                )}
                <span>
                  {check.label}
                  <span className="sr-only">{check.met ? ', met' : ', not met'}</span>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {breakdown.matched_skills.length + breakdown.missing_skills.length > 0 && (
        <>
          <h3 className="mt-5 text-sm font-medium">Skill gap</h3>
          <p className="text-muted-foreground mb-2 text-sm">
            {breakdown.missing_skills.length === 0
              ? 'You have every listed skill.'
              : `Not in your profile: ${breakdown.missing_skills.join(', ')}.`}
          </p>
          <SkillChips breakdown={breakdown} limit={20} />
        </>
      )}
    </Card>
  );
}
