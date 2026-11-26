import { useEffect } from 'react';
import { api } from './api';

/** What the browser reports. Saves, opens and reactions are recorded by the server. */
export type EventKind = 'impression' | 'apply_clicked';

type Event = { job_id: number; kind: EventKind };

const BATCH = 50;
const DELAY_MS = 2000;
const queue = new Map<string, Event>();
// Impressions count once per page load, however often a list re-renders.
const shown = new Set<number>();
let timer: ReturnType<typeof setTimeout> | undefined;

export async function flushEvents(keepalive = false): Promise<void> {
  if (timer !== undefined) clearTimeout(timer);
  timer = undefined;
  while (queue.size) {
    const batch = [...queue.entries()].slice(0, BATCH);
    batch.forEach(([key]) => queue.delete(key));
    try {
      await api('/events', {
        method: 'POST',
        body: { events: batch.map(([, event]) => event) },
        keepalive,
      });
    } catch {
      // Best effort: a lost event only makes ranking a little less personal.
      return;
    }
  }
}

export function recordEvent(jobId: number, kind: EventKind): void {
  if (kind === 'impression') {
    if (shown.has(jobId)) return;
    shown.add(jobId);
  }
  queue.set(`${jobId}:${kind}`, { job_id: jobId, kind });
  if (timer === undefined) timer = setTimeout(() => void flushEvents(), DELAY_MS);
}

/** Record that these postings were shown. */
export function useImpressions(jobIds: number[]): void {
  const key = jobIds.join(',');
  useEffect(() => {
    if (!key) return;
    key.split(',').forEach((id) => recordEvent(Number(id), 'impression'));
  }, [key]);
}

if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', () => void flushEvents(true));
}

/** For tests. */
export function resetEvents(): void {
  queue.clear();
  shown.clear();
  if (timer !== undefined) clearTimeout(timer);
  timer = undefined;
}
