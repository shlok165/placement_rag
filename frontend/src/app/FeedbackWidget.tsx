import { useMutation } from '@tanstack/react-query';
import { MessageCircleHeart } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link, useLocation } from 'react-router';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Alert } from '@/components/ui/display';
import { Field, Select, Textarea } from '@/components/ui/form';
import { Dialog } from '@/components/ui/overlay';
import { api, messageOf } from '@/lib/api';

export function FeedbackWidget() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState('idea');
  const [message, setMessage] = useState('');
  const send = useMutation({
    mutationFn: () =>
      api('/feedback', { method: 'POST', body: { category, message, page: pathname } }),
    onSuccess: () => {
      setOpen(false);
      setMessage('');
      toast.success('Thank you. The team will read this.');
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    send.mutate();
  };
  return (
    <footer className="text-muted-foreground mx-auto flex w-full max-w-6xl flex-wrap items-center gap-x-4 gap-y-1 px-4 pb-6 text-sm sm:px-6">
      <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
        <MessageCircleHeart aria-hidden />
        Give feedback
      </Button>
      <Link to="/survey" className="rounded-sm py-1 underline-offset-4 hover:underline">
        Usability survey
      </Link>
      <Link to="/privacy" className="rounded-sm py-1 underline-offset-4 hover:underline">
        Privacy
      </Link>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Give feedback"
        description="Coordinators see the message and the page it came from, not your name."
      >
        <form onSubmit={submit} className="flex flex-col gap-4">
          {send.isError && <Alert tone="danger">{messageOf(send.error)}</Alert>}
          <Field label="About">
            {(ids) => (
              <Select
                {...ids}
                value={category}
                onValueChange={setCategory}
                options={[
                  { value: 'idea', label: 'An idea' },
                  { value: 'problem', label: 'A problem' },
                  { value: 'praise', label: 'Something I like' },
                ]}
              />
            )}
          </Field>
          <Field label="Message">
            {(ids) => (
              <Textarea
                {...ids}
                required
                minLength={3}
                maxLength={2000}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
            )}
          </Field>
          <Button type="submit" className="self-end" loading={send.isPending}>
            Send
          </Button>
        </form>
      </Dialog>
    </footer>
  );
}
