import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { linkCitations } from './Answer';
import { parseEvents } from './stream';
import { App } from '@/App';
import { axeViolations, mockApi, renderPage, studentUser } from '@/test/render';

const message = {
  id: 9,
  role: 'assistant',
  content: 'Try **Backend Intern** at Acme [#3].',
  citations: [{ job_id: 3, title: 'Backend Intern', company: 'Acme' }],
  suggested_followups: ['Why does #3 fit me?'],
  pending_actions: [
    {
      id: 5,
      kind: 'save_job',
      label: 'Save Backend Intern at Acme',
      payload: { job_id: 3 },
      status: 'pending',
    },
  ],
  notice: null,
  stopped: false,
  feedback: null,
  created_at: '2031-01-01T00:00:00Z',
};

const sse = (...events: unknown[]) =>
  new Response(events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join(''), {
    headers: { 'Content-Type': 'text/event-stream' },
  });

const base = {
  'GET /auth/me': studentUser,
  'GET /notifications/unread': { unread: 0 },
  'GET /announcement': { id: null, message: null },
  'GET /chat/sessions': [],
  'GET /chat/status': {
    mode: 'mock',
    consent: true,
    quota: { limit: 30, used: 2, remaining: 28 },
  },
  'POST /chat/sessions': { id: 4, title: 'New conversation', updated_at: '2031-01-01T00:00:00Z' },
  'POST /chat/sessions/4/messages': sse(
    { type: 'status', text: 'Searching postings' },
    { type: 'delta', text: 'Try ' },
    { type: 'done', message },
  ),
};

describe('copilot', () => {
  it('asks for consent before first use', async () => {
    mockApi({
      ...base,
      'GET /auth/me': { ...studentUser, consent_at: null },
      'GET /chat/status': { ...base['GET /chat/status'], consent: false },
    });
    renderPage(<App />, '/copilot');
    const button = await screen.findByRole('button', { name: 'Turn on AI features' });
    expect(button).toBeDisabled();
    await userEvent.click(screen.getByLabelText('I agree to this use of my data'));
    expect(button).toBeEnabled();
    expect(screen.queryByLabelText('Message the copilot')).not.toBeInTheDocument();
  });

  it('streams an answer with citations, quota and a confirmable action', async () => {
    const calls = mockApi({
      ...base,
      'POST /chat/actions/5/confirm': { ...message.pending_actions[0], status: 'confirmed' },
    });
    const { container } = renderPage(<App />, '/copilot');
    expect(await screen.findByText('28 messages left today, out of 30')).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Message the copilot'), 'backend roles{Enter}');
    expect(await screen.findByText('Sources')).toBeInTheDocument();
    expect(screen.getByText('backend roles')).toBeInTheDocument();
    const links = screen.getAllByRole('link', { name: /Backend Intern/ });
    links.forEach((link) => expect(link).toHaveAttribute('href', '/jobs/3'));
    expect(screen.getByRole('button', { name: 'Why does #3 fit me?' })).toBeInTheDocument();
    expect(calls.some((c) => c.key.includes('/actions/'))).toBe(false);
    expect(await axeViolations(container)).toEqual([]);

    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.getByText('Saved', { selector: 'p' })).toBeInTheDocument());
  });

  it('explains when the daily limit is reached', async () => {
    mockApi({
      ...base,
      'GET /chat/status': {
        mode: 'mock',
        consent: true,
        quota: { limit: 30, used: 30, remaining: 0 },
      },
    });
    renderPage(<App />, '/copilot');
    expect(await screen.findByLabelText('Message the copilot')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });

  it('shows a plain message and a retry when a turn fails', async () => {
    mockApi({
      ...base,
      'POST /chat/sessions/4/messages': sse({ type: 'error', message: 'Please retry.' }),
    });
    renderPage(<App />, '/copilot');
    await userEvent.type(await screen.findByLabelText('Message the copilot'), 'hi{Enter}');
    expect(await screen.findByText('Please retry.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('never renders links that leave the portal', async () => {
    mockApi({
      ...base,
      'GET /chat/sessions/4/messages': [
        {
          ...message,
          content: '[click](https://evil.example) <img src=x> [#3]',
          pending_actions: [],
        },
      ],
    });
    const { container } = renderPage(<App />, '/copilot/4');
    await screen.findByText('Sources');
    expect(container.querySelector('a[href*="evil"]')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
  });

  it('lists, edits and forgets remembered facts', async () => {
    const calls = mockApi({
      ...base,
      'GET /memory': [
        { id: 1, kind: 'preference', text: 'Prefer Pune', created_at: '2031-01-01T00:00:00Z' },
      ],
      'DELETE /memory/1': new Response(null, { status: 204 }),
    });
    const { container } = renderPage(<App />, '/memory');
    expect(await screen.findByText('Prefer Pune')).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
    await userEvent.click(screen.getByRole('button', { name: 'Forget: Prefer Pune' }));
    await userEvent.click(screen.getByRole('button', { name: 'Forget' }));
    await waitFor(() => expect(calls.some((c) => c.key === 'DELETE /memory/1')).toBe(true));
  });

  it('parses partial event buffers', () => {
    const { events, rest } = parseEvents('data: {"type":"delta","text":"a"}\n\ndata: {"ty');
    expect(events).toEqual([{ type: 'delta', text: 'a' }]);
    expect(rest).toBe('data: {"ty');
  });

  it('links only citation markers', () => {
    expect(linkCitations('See [#12] and #13')).toBe('See [#12](/jobs/12) and #13');
  });
});
