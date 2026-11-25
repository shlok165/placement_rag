import { csrfHeaders, toApiError } from '@/lib/api';
import type { ChatMessage } from '@/lib/types';

export type StreamEvent =
  | { type: 'status'; text: string }
  | { type: 'delta'; text: string }
  | { type: 'done'; message: ChatMessage }
  | { type: 'error'; message: string };

/** Split a server-sent event buffer into complete events and the unfinished rest. */
export function parseEvents(buffer: string): { events: StreamEvent[]; rest: string } {
  const parts = buffer.split('\n\n');
  const rest = parts.pop() ?? '';
  const events = parts
    .filter((part) => part.startsWith('data: '))
    .map((part) => JSON.parse(part.slice(6)) as StreamEvent);
  return { events, rest };
}

export async function streamMessage(
  sessionId: number,
  text: string,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(`/api/chat/sessions/${sessionId}/messages`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
    body: JSON.stringify({ text }),
    signal,
  });
  if (!response.ok) throw await toApiError(response);
  if (!response.body) throw new Error('This browser cannot show streamed answers.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    const parsed = parseEvents(buffer + decoder.decode(value, { stream: true }));
    buffer = parsed.rest;
    parsed.events.forEach(onEvent);
  }
}
