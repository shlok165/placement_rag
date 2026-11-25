import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell, Bookmark, Clock, Sparkles } from 'lucide-react';
import { Link } from 'react-router';
import { JobCard } from './JobCard';
import { QueryState } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { Badge, Card, EmptyState, PageHeader } from '@/components/ui/display';
import { api } from '@/lib/api';
import { deadlineText, formatDateTime } from '@/lib/format';
import { useTitle } from '@/lib/title';
import type { AppNotification, SearchHit } from '@/lib/types';

export function SavedPage() {
  useTitle('Saved');
  const query = useQuery({ queryKey: ['saved'], queryFn: () => api<SearchHit[]>('/saved') });
  return (
    <>
      <PageHeader title="Saved postings" description="You get a reminder before these close." />
      <QueryState query={query}>
        {(hits) =>
          hits.length ? (
            <ul className="flex flex-col gap-4">
              {hits.map((hit) => (
                <li key={hit.job.id}>
                  <JobCard hit={hit} level="h2" />
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={Bookmark}
              title="Nothing saved yet"
              action={
                <Button asChild>
                  <Link to="/jobs">Browse postings</Link>
                </Button>
              }
            >
              Use the bookmark on any posting to keep it here.
            </EmptyState>
          )
        }
      </QueryState>
    </>
  );
}

const kinds = {
  new_match: { icon: Sparkles, text: 'New posting that fits your profile' },
  deadline_soon: { icon: Clock, text: 'Closing soon' },
} as const;

export function NotificationsPage() {
  useTitle('Notifications');
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ['notifications'],
    queryFn: () => api<AppNotification[]>('/notifications'),
  });
  const refresh = () => {
    client.invalidateQueries({ queryKey: ['notifications'] });
    client.invalidateQueries({ queryKey: ['unread'] });
    client.invalidateQueries({ queryKey: ['home'] });
  };
  const readAll = useMutation({
    mutationFn: () => api<void>('/notifications/read', { method: 'POST' }),
    onSuccess: refresh,
  });
  const readOne = useMutation({
    mutationFn: (id: number) => api<void>(`/notifications/${id}/read`, { method: 'POST' }),
    onSuccess: refresh,
  });
  const unread = query.data?.some((n) => !n.read_at);

  return (
    <>
      <PageHeader
        title="Notifications"
        actions={
          <Button
            variant="secondary"
            disabled={!unread}
            title={unread ? undefined : 'Everything is read'}
            onClick={() => readAll.mutate()}
          >
            Mark all as read
          </Button>
        }
      />
      <QueryState query={query}>
        {(items) =>
          items.length ? (
            <Card>
              <ul className="divide-y">
                {items.map((item) => {
                  const kind = kinds[item.type as keyof typeof kinds];
                  const Icon = kind?.icon ?? Bell;
                  return (
                    <li key={item.id} className="relative flex items-start gap-3 p-4">
                      <Icon className="text-primary mt-0.5 size-5 shrink-0" aria-hidden />
                      <div className="min-w-0 flex-1">
                        <p className="text-muted-foreground text-sm">{kind?.text ?? 'Update'}</p>
                        <Link
                          to={`/jobs/${item.payload.job_id}`}
                          onClick={() => !item.read_at && readOne.mutate(item.id)}
                          className="font-medium after:absolute after:inset-0"
                        >
                          {item.payload.title}
                        </Link>
                        <p className="text-muted-foreground text-sm">
                          {item.payload.company} · {deadlineText(item.payload.deadline ?? null)} ·{' '}
                          {formatDateTime(item.created_at)}
                        </p>
                      </div>
                      {!item.read_at && <Badge tone="accent">New</Badge>}
                    </li>
                  );
                })}
              </ul>
            </Card>
          ) : (
            <EmptyState icon={Bell} title="No notifications yet">
              You are told here when a new posting fits your profile, and before saved postings
              close.
            </EmptyState>
          )
        }
      </QueryState>
    </>
  );
}
