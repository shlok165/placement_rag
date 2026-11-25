import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Check, ThumbsDown, ThumbsUp, X } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import { Answer } from './Answer';
import { Button } from '@/components/ui/button';
import { Alert, Card } from '@/components/ui/display';
import { Field, Textarea } from '@/components/ui/form';
import { Dialog } from '@/components/ui/overlay';
import { api, messageOf } from '@/lib/api';
import type { ChatMessage, PendingAction } from '@/lib/types';

const doneText: Record<PendingAction['kind'], string> = {
  save_job: 'Saved',
  track_application: 'Tracker updated',
  update_preferences: 'Preferences updated',
  remember: 'The copilot will remember this',
};
const confirmText: Record<PendingAction['kind'], string> = {
  save_job: 'Save',
  track_application: 'Update tracker',
  update_preferences: 'Apply change',
  remember: 'Remember',
};

function ActionCard({
  action,
  onResolved,
}: {
  action: PendingAction;
  onResolved: (action: PendingAction) => void;
}) {
  const client = useQueryClient();
  const resolve = useMutation({
    mutationFn: (verb: 'confirm' | 'reject') =>
      api<PendingAction>(`/chat/actions/${action.id}/${verb}`, { method: 'POST' }),
    onSuccess: (updated) => {
      onResolved(updated);
      if (updated.status !== 'confirmed') return;
      toast.success(doneText[updated.kind]);
      for (const key of ['saved', 'applications', 'profile', 'memory', 'home', 'search', 'job'])
        client.invalidateQueries({ queryKey: [key] });
    },
    onError: (error) => toast.error(messageOf(error)),
  });
  return (
    <Card className="flex flex-wrap items-center gap-3 p-3">
      <p className="min-w-40 flex-1 text-sm font-medium">{action.label}</p>
      {action.status === 'pending' ? (
        <div className="flex gap-2">
          <Button
            size="sm"
            loading={resolve.isPending && resolve.variables === 'confirm'}
            onClick={() => resolve.mutate('confirm')}
          >
            {confirmText[action.kind]}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={resolve.isPending}
            onClick={() => resolve.mutate('reject')}
          >
            No thanks
          </Button>
        </div>
      ) : (
        <p className="text-muted-foreground flex items-center gap-1 text-sm">
          {action.status === 'confirmed' ? (
            <Check className="text-success size-4" aria-hidden />
          ) : (
            <X className="size-4" aria-hidden />
          )}
          {action.status === 'confirmed' ? doneText[action.kind] : 'Not done'}
        </p>
      )}
    </Card>
  );
}

function Rating({ message }: { message: ChatMessage }) {
  const [rating, setRating] = useState(message.feedback);
  const [asking, setAsking] = useState(false);
  const [comment, setComment] = useState('');
  const send = useMutation({
    mutationFn: (body: { rating: 'up' | 'down'; comment?: string }) =>
      api<void>(`/chat/messages/${message.id}/feedback`, { method: 'POST', body }),
    onError: (error) => {
      setRating(message.feedback);
      toast.error(messageOf(error));
    },
  });
  const rate = (value: 'up' | 'down') => {
    setRating(value);
    send.mutate({ rating: value });
    setAsking(true);
  };
  return (
    <div className="flex">
      <Button
        variant="ghost"
        size="icon"
        aria-label="Good answer"
        aria-pressed={rating === 'up'}
        onClick={() => rate('up')}
      >
        <ThumbsUp className={rating === 'up' ? 'text-primary' : undefined} aria-hidden />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Poor answer"
        aria-pressed={rating === 'down'}
        onClick={() => rate('down')}
      >
        <ThumbsDown className={rating === 'down' ? 'text-danger' : undefined} aria-hidden />
      </Button>
      <Dialog
        open={asking}
        onOpenChange={setAsking}
        title={rating === 'up' ? 'What was good about it?' : 'What went wrong?'}
        description="Optional. Coordinators can see this question and your comment."
      >
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (rating && comment.trim())
              send.mutate(
                { rating, comment: comment.trim() },
                { onSuccess: () => toast.success('Thank you') },
              );
            setAsking(false);
          }}
        >
          <Field label="Comment">
            {(ids) => (
              <Textarea
                {...ids}
                maxLength={1000}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
            )}
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setAsking(false)}>
              Skip
            </Button>
            <Button type="submit">Send</Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}

export function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <p className="bg-accent text-accent-foreground max-w-[85%] rounded-lg px-4 py-2.5 text-sm break-words whitespace-pre-wrap">
        <span className="sr-only">You: </span>
        {text}
      </p>
    </div>
  );
}

export function AssistantMessage({
  message,
  latest,
  onFollowup,
  onAction,
}: {
  message: ChatMessage;
  latest: boolean;
  onFollowup: (text: string) => void;
  onAction: (action: PendingAction) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <span className="sr-only">Copilot:</span>
      {message.notice && <Alert tone="warning">{message.notice}</Alert>}
      <Answer text={message.content} citations={message.citations} />
      {message.stopped && <p className="text-muted-foreground text-sm">You stopped this answer.</p>}
      {message.citations.length > 0 && (
        <div>
          <p className="text-muted-foreground text-xs font-medium">Sources</p>
          <ul className="mt-1 flex flex-wrap gap-2">
            {message.citations.map((c) => (
              <li key={c.job_id}>
                <Link
                  to={`/jobs/${c.job_id}`}
                  className="bg-card hover:bg-muted flex min-h-9 items-center gap-1.5 rounded-full border px-3 text-sm"
                >
                  <span className="text-muted-foreground tabular">#{c.job_id}</span>
                  <span className="max-w-64 truncate">
                    {c.title}, {c.company}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
      {message.pending_actions.map((action) => (
        <ActionCard key={action.id} action={action} onResolved={onAction} />
      ))}
      <div className="flex flex-wrap items-center gap-2">
        {message.content && !message.stopped && <Rating message={message} />}
        {latest &&
          message.suggested_followups.map((text) => (
            <Button key={text} variant="secondary" size="sm" onClick={() => onFollowup(text)}>
              {text}
            </Button>
          ))}
      </div>
    </div>
  );
}
