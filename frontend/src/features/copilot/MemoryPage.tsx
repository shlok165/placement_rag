import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Brain, Pencil, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import { Breadcrumb } from '@/components/Breadcrumb';
import { QueryState } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { Badge, Card, EmptyState, PageHeader } from '@/components/ui/display';
import { Field, Input } from '@/components/ui/form';
import { ConfirmDialog, Dialog } from '@/components/ui/overlay';
import { api, messageOf } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useTitle } from '@/lib/title';
import type { MemoryFact } from '@/lib/types';

export function MemoryPage() {
  useTitle('What the copilot remembers');
  const client = useQueryClient();
  const query = useQuery({ queryKey: ['memory'], queryFn: () => api<MemoryFact[]>('/memory') });
  const [editing, setEditing] = useState<MemoryFact | null>(null);
  const [text, setText] = useState('');
  const [deleting, setDeleting] = useState<MemoryFact | null>(null);

  const refresh = () => client.invalidateQueries({ queryKey: ['memory'] });
  const onError = (error: unknown) => {
    toast.error(messageOf(error));
  };
  const save = useMutation({
    mutationFn: (fact: MemoryFact) =>
      api<MemoryFact>(`/memory/${fact.id}`, { method: 'PUT', body: { text } }),
    onSuccess: () => {
      setEditing(null);
      toast.success('Updated');
      refresh();
    },
    onError,
  });
  const remove = useMutation({
    mutationFn: (fact: MemoryFact) => api<void>(`/memory/${fact.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Forgotten');
      refresh();
    },
    onError,
  });

  return (
    <>
      <PageHeader
        breadcrumb={
          <Breadcrumb items={[['/copilot', 'Copilot']]} current="What the copilot remembers" />
        }
        title="What the copilot remembers"
        description="Only facts you confirmed are kept. They are added to each conversation, so the copilot does not have to ask again."
      />
      <QueryState query={query}>
        {(facts) =>
          facts.length ? (
            <Card>
              <ul className="divide-y">
                {facts.map((fact) => (
                  <li key={fact.id} className="flex items-center gap-3 p-4">
                    <div className="min-w-0 flex-1">
                      <p className="break-words">{fact.text}</p>
                      <p className="text-muted-foreground mt-1 flex items-center gap-2 text-sm">
                        <Badge>{fact.kind === 'preference' ? 'Preference' : 'Fact'}</Badge>
                        Added {formatDate(fact.created_at)}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Edit: ${fact.text}`}
                      onClick={() => {
                        setText(fact.text);
                        setEditing(fact);
                      }}
                    >
                      <Pencil aria-hidden />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Forget: ${fact.text}`}
                      onClick={() => setDeleting(fact)}
                    >
                      <Trash2 aria-hidden />
                    </Button>
                  </li>
                ))}
              </ul>
            </Card>
          ) : (
            <EmptyState
              icon={Brain}
              title="Nothing remembered yet"
              action={
                <Button asChild>
                  <Link to="/copilot">Open the copilot</Link>
                </Button>
              }
            >
              Tell the copilot something lasting, such as “I am targeting summer 2027”. It asks
              before keeping it.
            </EmptyState>
          )
        }
      </QueryState>
      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)} title="Edit">
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (editing) save.mutate(editing);
          }}
        >
          <Field label="Remembered as">
            {(ids) => (
              <Input
                {...ids}
                required
                minLength={3}
                maxLength={300}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            )}
          </Field>
          <Button type="submit" className="self-end" loading={save.isPending}>
            Save
          </Button>
        </form>
      </Dialog>
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="Forget this?"
        description={deleting?.text}
        confirmLabel="Forget"
        destructive
        onConfirm={() => deleting && remove.mutate(deleting)}
      />
    </>
  );
}
