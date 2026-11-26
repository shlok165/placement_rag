import { describe, expect, it } from 'vitest';
import { flushEvents, recordEvent } from './events';
import { mockApi } from '@/test/render';

describe('behaviour events', () => {
  it('sends each impression once per page load, with other kinds, in one batch', async () => {
    const calls = mockApi({ 'POST /events': { recorded: 2 } });
    recordEvent(7, 'impression');
    recordEvent(7, 'impression');
    recordEvent(7, 'apply_clicked');
    await flushEvents();
    recordEvent(7, 'impression');
    await flushEvents();
    const posts = calls.filter((c) => c.key === 'POST /events');
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({
      events: [
        { job_id: 7, kind: 'impression' },
        { job_id: 7, kind: 'apply_clicked' },
      ],
    });
  });

  it('splits large batches and survives a failed request', async () => {
    const calls = mockApi({});
    for (let id = 1; id <= 60; id += 1) recordEvent(id, 'impression');
    await expect(flushEvents()).resolves.toBeUndefined();
    expect(calls.filter((c) => c.key === 'POST /events')).toHaveLength(1);
  });
});
