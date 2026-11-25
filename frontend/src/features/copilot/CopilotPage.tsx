import { useQuery, useQueryClient } from '@tanstack/react-query';
import { History, Loader2, MessageSquarePlus, Send, Square, Trash2 } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import { toast } from 'sonner';
import { Answer } from './Answer';
import { AssistantMessage, UserBubble } from './MessageParts';
import { streamMessage } from './stream';
import { QueryState } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { Alert, Badge } from '@/components/ui/display';
import { Sheet, Tooltip } from '@/components/ui/overlay';
import { ConsentCard } from '@/features/student/ConsentCard';
import { api, ApiError, messageOf } from '@/lib/api';
import { useUser } from '@/lib/auth';
import { formatDateTime, plural } from '@/lib/format';
import { useTitle } from '@/lib/title';
import type { ChatMessage, ChatSession, ChatStatus, PendingAction } from '@/lib/types';

const starters = [
  'Recommend postings for me',
  'What is closing this week?',
  'Find remote data science internships',
  'What does my profile say?',
];

type Live = { question: string; status: string; text: string };

function Sessions({
  sessions,
  activeId,
  onDelete,
  onOpen,
}: {
  sessions: ChatSession[];
  activeId: number | null;
  onDelete: (id: number) => void;
  onOpen: () => void;
}) {
  if (!sessions.length)
    return <p className="text-muted-foreground text-sm">Past conversations appear here.</p>;
  return (
    <ul className="flex flex-col gap-1">
      {sessions.map((session) => (
        <li key={session.id} className="flex items-center gap-1">
          <Link
            to={`/copilot/${session.id}`}
            onClick={onOpen}
            aria-current={session.id === activeId ? 'page' : undefined}
            className="hover:bg-muted aria-[current=page]:bg-accent aria-[current=page]:text-accent-foreground flex min-h-11 min-w-0 flex-1 flex-col justify-center rounded-md px-3 py-1 text-sm"
          >
            <span className="truncate">{session.title}</span>
            <span className="text-muted-foreground text-xs">
              {formatDateTime(session.updated_at)}
            </span>
          </Link>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Delete conversation: ${session.title}`}
            onClick={() => onDelete(session.id)}
          >
            <Trash2 aria-hidden />
          </Button>
        </li>
      ))}
    </ul>
  );
}

function Conversation({ sessionId, status }: { sessionId: number | null; status: ChatStatus }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [draft, setDraft] = useState('');
  const [live, setLive] = useState<Live | null>(null);
  const [error, setError] = useState<{ text: string; retry: string | null } | null>(null);
  const controller = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const streamingInto = useRef<number | null>(null);

  const key = ['chat', sessionId];
  const query = useQuery({
    queryKey: key,
    queryFn: () => api<ChatMessage[]>(`/chat/sessions/${sessionId}/messages`),
    enabled: sessionId !== null && streamingInto.current !== sessionId,
  });
  const messages = sessionId === null ? [] : (query.data ?? []);

  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' });
  }, [messages.length, live?.text, live?.status]);

  useEffect(() => () => controller.current?.abort(), []);

  const send = async (raw: string) => {
    const text = raw.trim();
    if (!text || live) return;
    setDraft('');
    setError(null);
    setLive({ question: text, status: 'Sending', text: '' });
    const abort = new AbortController();
    controller.current = abort;
    let id = sessionId;
    try {
      if (id === null) {
        const created = await api<ChatSession>('/chat/sessions', { method: 'POST' });
        id = created.id;
        streamingInto.current = id;
        client.setQueryData(['chat', id], []);
        navigate(`/copilot/${id}`, { replace: true });
      }
      await streamMessage(
        id,
        text,
        (event) => {
          if (event.type === 'status') setLive((l) => l && { ...l, status: event.text });
          if (event.type === 'delta') setLive((l) => l && { ...l, text: l.text + event.text });
          if (event.type === 'error') setError({ text: event.message, retry: text });
          if (event.type === 'done') {
            const asked: ChatMessage = {
              id: -event.message.id,
              role: 'user',
              content: text,
              citations: [],
              suggested_followups: [],
              pending_actions: [],
              notice: null,
              stopped: false,
              feedback: null,
              created_at: event.message.created_at,
            };
            client.setQueryData<ChatMessage[]>(['chat', id], (old = []) => [
              ...old,
              asked,
              event.message,
            ]);
          }
        },
        abort.signal,
      );
    } catch (cause) {
      if (abort.signal.aborted) {
        // The server stores what was shown before the stop; give it a moment, then reload.
        await new Promise((resolve) => setTimeout(resolve, 600));
      } else {
        const retry = cause instanceof ApiError && cause.code === 'quota' ? null : text;
        setError({ text: messageOf(cause), retry });
      }
    } finally {
      streamingInto.current = null;
      setLive(null);
      controller.current = null;
      if (id !== null && abort.signal.aborted) client.invalidateQueries({ queryKey: ['chat', id] });
      client.invalidateQueries({ queryKey: ['chat-status'] });
      client.invalidateQueries({ queryKey: ['chat-sessions'] });
      input.current?.focus();
    }
  };

  const updateAction = (action: PendingAction) =>
    client.setQueryData<ChatMessage[]>(key, (old = []) =>
      old.map((m) => ({
        ...m,
        pending_actions: m.pending_actions.map((a) => (a.id === action.id ? action : a)),
      })),
    );

  const { remaining, limit } = status.quota;
  const outOfQuota = remaining <= 0;
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send(draft);
    }
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void send(draft);
  };
  const empty = messages.length === 0 && !live;

  return (
    <div className="flex min-h-[calc(100dvh-11rem)] flex-col">
      <div
        className="flex flex-1 flex-col gap-6 pb-6"
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        aria-busy={!!live}
        aria-label="Conversation"
      >
        {sessionId !== null && !live && query.isPending ? (
          <QueryState query={query}>{() => null}</QueryState>
        ) : empty ? (
          <div className="my-auto flex flex-col items-center gap-4 py-8 text-center">
            <div>
              <h2 className="text-lg font-semibold">What are you looking for?</h2>
              <p className="text-muted-foreground mt-1 max-w-md text-sm">
                The copilot answers only from postings in this portal, links every one it mentions,
                and asks before it changes anything.
              </p>
            </div>
            <div className="grid w-full max-w-xl gap-2 sm:grid-cols-2">
              {starters.map((text) => (
                <Button
                  key={text}
                  variant="secondary"
                  className="h-auto min-h-12 justify-start py-2 text-left whitespace-normal"
                  disabled={outOfQuota}
                  onClick={() => send(text)}
                >
                  {text}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message, index) =>
            message.role === 'user' ? (
              <UserBubble key={message.id} text={message.content} />
            ) : (
              <AssistantMessage
                key={message.id}
                message={message}
                latest={index === messages.length - 1 && !live}
                onFollowup={send}
                onAction={updateAction}
              />
            ),
          )
        )}
        {live && (
          <>
            <UserBubble text={live.question} />
            {live.text ? (
              <Answer text={live.text} citations={[]} />
            ) : (
              <p className="text-muted-foreground flex items-center gap-2 text-sm">
                <Loader2 className="size-4 animate-spin" aria-hidden />
                {live.status}…
              </p>
            )}
          </>
        )}
        {error && (
          <Alert
            tone="danger"
            title="That did not work"
            action={
              error.retry && (
                <Button variant="secondary" size="sm" onClick={() => send(error.retry!)}>
                  Try again
                </Button>
              )
            }
          >
            {error.text}
          </Alert>
        )}
        <div ref={end} className="scroll-mb-40" />
      </div>

      <form
        onSubmit={submit}
        className="bg-background sticky bottom-0 -mx-1 border-t px-1 pt-3 pb-2"
      >
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs">
          <span className="text-muted-foreground" aria-live="polite">
            {plural(remaining, 'message')} left today, out of {limit}
          </span>
          {status.mode === 'mock' && (
            <Tooltip content="Answers come from built-in rules over the real postings. No AI provider is contacted.">
              <Badge tone="info" tabIndex={0}>
                Mock mode
              </Badge>
            </Tooltip>
          )}
        </div>
        <div className="flex items-end gap-2">
          <textarea
            ref={input}
            aria-label="Message the copilot"
            rows={1}
            maxLength={2000}
            value={draft}
            disabled={outOfQuota}
            placeholder={
              outOfQuota
                ? 'Your messages reset at midnight UTC'
                : 'Ask about postings, deadlines or fit'
            }
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            className="border-input bg-card placeholder:text-muted-foreground field-sizing-content max-h-40 min-h-12 flex-1 resize-none rounded-md border px-3 py-3 text-base disabled:opacity-60 sm:text-sm"
          />
          {live ? (
            <Button
              variant="secondary"
              className="h-12 sm:h-12"
              onClick={() => controller.current?.abort()}
            >
              <Square aria-hidden />
              Stop
            </Button>
          ) : (
            <Button
              type="submit"
              className="h-12 sm:h-12"
              disabled={!draft.trim() || outOfQuota}
              title={
                outOfQuota
                  ? 'No messages left today'
                  : draft.trim()
                    ? undefined
                    : 'Write a message first'
              }
            >
              <Send aria-hidden />
              Send
            </Button>
          )}
        </div>
      </form>
    </div>
  );
}

export function CopilotPage() {
  useTitle('Copilot');
  const params = useParams();
  const sessionId = params.id ? Number(params.id) : null;
  const navigate = useNavigate();
  const client = useQueryClient();
  const { data: user } = useUser();
  const [historyOpen, setHistoryOpen] = useState(false);
  // Keeps one Conversation mounted while a new chat gets its id, so the stream is not cut.
  const [chatKey, setChatKey] = useState(0);
  const [lastId, setLastId] = useState(sessionId);
  if (sessionId !== lastId) {
    if (lastId !== null) setChatKey((k) => k + 1);
    setLastId(sessionId);
  }

  const status = useQuery({
    queryKey: ['chat-status', user?.consent_at],
    queryFn: () => api<ChatStatus>('/chat/status'),
  });
  const sessions = useQuery({
    queryKey: ['chat-sessions'],
    queryFn: () => api<ChatSession[]>('/chat/sessions'),
  });

  const remove = async (id: number) => {
    try {
      await api<void>(`/chat/sessions/${id}`, { method: 'DELETE' });
      toast.success('Conversation deleted');
      client.invalidateQueries({ queryKey: ['chat-sessions'] });
      if (id === sessionId) navigate('/copilot');
    } catch (error) {
      toast.error(messageOf(error));
    }
  };

  const list = (
    <Sessions
      sessions={sessions.data ?? []}
      activeId={sessionId}
      onDelete={remove}
      onOpen={() => setHistoryOpen(false)}
    />
  );

  return (
    <div className="lg:grid lg:grid-cols-[1fr_15rem] lg:gap-8">
      <div className="min-w-0">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-2xl font-semibold">Copilot</h1>
          <div className="flex gap-2">
            <Button variant="ghost" className="lg:hidden" onClick={() => setHistoryOpen(true)}>
              <History aria-hidden />
              History
            </Button>
            <Button asChild variant="secondary">
              <Link to="/copilot">
                <MessageSquarePlus aria-hidden />
                New chat
              </Link>
            </Button>
          </div>
        </div>
        <QueryState query={status}>
          {(data) =>
            data.consent ? (
              <Conversation key={chatKey} sessionId={sessionId} status={data} />
            ) : (
              <ConsentCard reason="The copilot needs your agreement before its first use." />
            )
          }
        </QueryState>
      </div>
      <aside className="sticky top-20 hidden self-start lg:block" aria-label="Conversations">
        <h2 className="mb-2 text-sm font-semibold">Conversations</h2>
        {list}
        <Button asChild variant="link" className="mt-4 h-auto px-0">
          <Link to="/memory">What the copilot remembers</Link>
        </Button>
      </aside>
      <Sheet open={historyOpen} onOpenChange={setHistoryOpen} title="Conversations" side="right">
        {list}
        <Button asChild variant="link" className="mt-4 h-auto justify-start px-0">
          <Link to="/memory">What the copilot remembers</Link>
        </Button>
      </Sheet>
    </div>
  );
}
