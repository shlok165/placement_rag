import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { toast } from 'sonner';
import { QueryState } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { Badge, Card, PageHeader } from '@/components/ui/display';
import { Field, Textarea } from '@/components/ui/form';
import { api, messageOf } from '@/lib/api';
import { formatDateTime, plural } from '@/lib/format';
import { useTitle } from '@/lib/title';

type Announcement = { id: number; message: string; is_active: boolean; created_at: string };
type Feedback = {
  items: { id: number; category: string; page: string; message: string; created_at: string }[];
  sus: { responses: number; mean: number | null };
};

export function AnnouncementsPage() {
  useTitle('Announcements');
  const client = useQueryClient();
  const [message, setMessage] = useState('');
  const list = useQuery({
    queryKey: ['admin-announcements'],
    queryFn: () => api<Announcement[]>('/admin/announcements'),
  });
  const feedback = useQuery({
    queryKey: ['admin-feedback'],
    queryFn: () => api<Feedback>('/admin/feedback'),
  });
  const refresh = () => {
    client.invalidateQueries({ queryKey: ['admin-announcements'] });
    client.invalidateQueries({ queryKey: ['announcement'] });
  };
  const create = useMutation({
    mutationFn: () => api('/admin/announcements', { method: 'POST', body: { message } }),
    onSuccess: () => {
      setMessage('');
      toast.success('Announcement is showing to students');
      refresh();
    },
    onError: (error) => toast.error(messageOf(error)),
  });
  const toggle = useMutation({
    mutationFn: ({ id, show }: { id: number; show: boolean }) =>
      api<void>(`/admin/announcements/${id}/${show ? 'show' : 'hide'}`, { method: 'POST' }),
    onSuccess: refresh,
    onError: (error) => toast.error(messageOf(error)),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate();
  };

  return (
    <>
      <PageHeader
        title="Announcements and feedback"
        description="One banner is shown to all students at a time."
      />
      <div className="grid items-start gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <form onSubmit={submit} className="flex flex-col gap-4">
            <Field label="New announcement" hint={`${message.length} of 300 characters`}>
              {(ids) => (
                <Textarea
                  {...ids}
                  required
                  minLength={5}
                  maxLength={300}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                />
              )}
            </Field>
            <Button type="submit" className="self-start" loading={create.isPending}>
              Show to students
            </Button>
          </form>
          <div className="mt-6">
            <QueryState query={list}>
              {(items) => (
                <ul className="divide-y text-sm">
                  {items.map((item) => (
                    <li key={item.id} className="flex items-start justify-between gap-4 py-3">
                      <div>
                        <p>{item.message}</p>
                        <p className="text-muted-foreground mt-1">
                          {formatDateTime(item.created_at)}{' '}
                          {item.is_active && <Badge tone="success">Showing</Badge>}
                        </p>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => toggle.mutate({ id: item.id, show: !item.is_active })}
                      >
                        {item.is_active ? 'Hide' : 'Show again'}
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </QueryState>
          </div>
        </Card>
        <Card className="p-5">
          <h2 className="font-semibold">Feedback from users</h2>
          <QueryState query={feedback}>
            {(data) => (
              <>
                <p className="text-muted-foreground mt-1 text-sm">
                  Usability survey: {plural(data.sus.responses, 'response')}
                  {data.sus.mean !== null && `, mean SUS score ${data.sus.mean}`}
                </p>
                {data.items.length === 0 ? (
                  <p className="text-muted-foreground mt-4 text-sm">No feedback yet.</p>
                ) : (
                  <ul className="mt-3 divide-y text-sm">
                    {data.items.map((item) => (
                      <li key={item.id} className="py-3">
                        <p className="text-muted-foreground">
                          <Badge>{item.category}</Badge> {item.page} ·{' '}
                          {formatDateTime(item.created_at)}
                        </p>
                        <p className="mt-1 break-words">{item.message}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </QueryState>
        </Card>
      </div>
    </>
  );
}
