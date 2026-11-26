import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarPlus, Copy, Download } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/display';
import { Field, Input } from '@/components/ui/form';
import { api, messageOf } from '@/lib/api';
import { formatDate } from '@/lib/format';

type FeedStatus = { active: boolean; created_at: string | null; url?: string };

/** Deadlines of saved and tracked postings, as a file or a private subscription link. */
export function CalendarCard() {
  const client = useQueryClient();
  const [link, setLink] = useState<string | null>(null);
  const [status, setStatus] = useState('');
  const feed = useQuery({
    queryKey: ['calendar-feed'],
    queryFn: () => api<FeedStatus>('/calendar/feed'),
  });
  const create = useMutation({
    mutationFn: () => api<FeedStatus>('/calendar/feed', { method: 'POST' }),
    onSuccess: (data) => {
      setLink(data.url ?? null);
      setStatus('');
      client.setQueryData(['calendar-feed'], { active: true, created_at: data.created_at });
    },
    onError: (error) => toast.error(messageOf(error)),
  });
  const revoke = useMutation({
    mutationFn: () => api<void>('/calendar/feed', { method: 'DELETE' }),
    onSuccess: () => {
      setLink(null);
      client.setQueryData(['calendar-feed'], { active: false, created_at: null });
      toast.success('The calendar link no longer works');
    },
    onError: (error) => toast.error(messageOf(error)),
  });
  const copy = async () => {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      setStatus('Link copied');
    } catch {
      setStatus('Copying is blocked here. Select the link and copy it instead.');
    }
  };
  const active = feed.data?.active ?? false;

  return (
    <Card className="p-5">
      <h2 className="font-semibold">Deadlines in your calendar</h2>
      <p className="text-muted-foreground mt-1 text-sm">
        Last days to apply for the postings you saved or track, with a reminder the day before.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button asChild variant="secondary">
          <a href="/api/calendar/deadlines.ics" download>
            <Download aria-hidden />
            Download .ics file
          </a>
        </Button>
        <Button variant="secondary" loading={create.isPending} onClick={() => create.mutate()}>
          <CalendarPlus aria-hidden />
          {active ? 'Make a new subscription link' : 'Make a subscription link'}
        </Button>
        {active && (
          <Button variant="ghost" loading={revoke.isPending} onClick={() => revoke.mutate()}>
            Turn off the link
          </Button>
        )}
      </div>
      {link && (
        <div className="mt-4">
          <Field
            label="Subscription link"
            hint="Anyone with this link can see these deadlines. It is shown only now. A new link turns off the old one."
          >
            {(ids) => <Input {...ids} readOnly value={link} onFocus={(e) => e.target.select()} />}
          </Field>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <Button size="sm" variant="secondary" onClick={copy}>
              <Copy aria-hidden />
              Copy link
            </Button>
            <p className="text-muted-foreground text-sm" role="status" aria-live="polite">
              {status}
            </p>
          </div>
        </div>
      )}
      {active && !link && feed.data?.created_at && (
        <p className="text-muted-foreground mt-3 text-sm">
          A subscription link made on {formatDate(feed.data.created_at)} is working.
        </p>
      )}
    </Card>
  );
}
