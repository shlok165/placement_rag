import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy, UserPlus } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Alert, Card, EmptyState, LoadingRows, PageHeader } from '@/components/ui/display';
import { Field, Input } from '@/components/ui/form';
import { ConfirmDialog } from '@/components/ui/overlay';
import { api, messageOf } from '@/lib/api';
import { useUser, type User } from '@/lib/auth';
import { useTitle } from '@/lib/title';

type Invite = { id: number; email: string; expires_at: string };

export function TeamPage() {
  useTitle('Team');
  const client = useQueryClient();
  const { data: me } = useUser();
  const team = useQuery({ queryKey: ['team'], queryFn: () => api<User[]>('/admin/team') });
  const invites = useQuery({
    queryKey: ['invites'],
    queryFn: () => api<Invite[]>('/admin/team/invites'),
  });
  const [email, setEmail] = useState('');
  const [link, setLink] = useState<string | null>(null);
  const [removing, setRemoving] = useState<User | null>(null);

  const invite = useMutation({
    mutationFn: () =>
      api<Invite & { link: string }>('/admin/team/invites', { method: 'POST', body: { email } }),
    onSuccess: (created) => {
      setLink(`${window.location.origin}${created.link}`);
      setEmail('');
      client.invalidateQueries({ queryKey: ['invites'] });
    },
  });
  const revoke = useMutation({
    mutationFn: (id: number) => api<void>(`/admin/team/invites/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Invite revoked');
      client.invalidateQueries({ queryKey: ['invites'] });
    },
    onError: (error) => toast.error(messageOf(error)),
  });
  const deactivate = useMutation({
    mutationFn: (id: number) => api<void>(`/admin/team/${id}/deactivate`, { method: 'POST' }),
    onSuccess: () => {
      toast.success('Coordinator removed');
      client.invalidateQueries({ queryKey: ['team'] });
    },
    onError: (error) => toast.error(messageOf(error)),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setLink(null);
    invite.mutate();
  };

  return (
    <>
      <PageHeader
        title="Team"
        description="Coordinators can manage postings and see portal analytics. Email sending is not set up, so you share the invite link yourself."
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="font-semibold">Invite a coordinator</h2>
          <form onSubmit={submit} className="mt-4 flex flex-col gap-4">
            <Field label="Email" error={invite.isError ? messageOf(invite.error) : null}>
              {(ids) => (
                <Input
                  {...ids}
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              )}
            </Field>
            <Button type="submit" loading={invite.isPending} className="self-start">
              <UserPlus aria-hidden />
              Create invite link
            </Button>
          </form>
          {link && (
            <Alert
              tone="success"
              title="Invite link ready"
              className="mt-4"
              action={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    navigator.clipboard.writeText(link).then(
                      () => toast.success('Link copied'),
                      () => toast.error('Copy failed. Select the link and copy it.'),
                    )
                  }
                >
                  <Copy aria-hidden />
                  Copy
                </Button>
              }
            >
              <p className="break-all">{link}</p>
              <p className="mt-1">Valid for 7 days. It is shown only once.</p>
            </Alert>
          )}
          {!!invites.data?.length && (
            <div className="mt-6">
              <h3 className="text-sm font-medium">Open invites</h3>
              <ul className="mt-2 divide-y">
                {invites.data.map((item) => (
                  <li
                    key={item.id}
                    className="flex items-center justify-between gap-3 py-2 text-sm"
                  >
                    <span className="min-w-0 truncate">{item.email}</span>
                    <Button variant="ghost" size="sm" onClick={() => revoke.mutate(item.id)}>
                      Revoke
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
        <Card className="p-5">
          <h2 className="font-semibold">Coordinators</h2>
          {team.isPending ? (
            <div className="mt-4">
              <LoadingRows rows={2} />
            </div>
          ) : team.data?.length ? (
            <ul className="mt-2 divide-y">
              {team.data.map((person) => (
                <li key={person.id} className="flex items-center justify-between gap-3 py-3">
                  <div className="min-w-0 text-sm">
                    <p className="truncate font-medium">{person.full_name}</p>
                    <p className="text-muted-foreground truncate">{person.email}</p>
                  </div>
                  {person.id === me?.id ? (
                    <span className="text-muted-foreground text-sm">You</span>
                  ) : (
                    <Button variant="ghost" size="sm" onClick={() => setRemoving(person)}>
                      Remove
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={UserPlus} title="No coordinators yet" />
          )}
        </Card>
      </div>
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={`Remove ${removing?.full_name ?? 'coordinator'}?`}
        description="They are signed out at once and can no longer use the portal. Postings they added stay."
        confirmLabel="Remove"
        destructive
        onConfirm={() => removing && deactivate.mutate(removing.id)}
      />
    </>
  );
}
