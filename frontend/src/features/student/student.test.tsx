import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Toaster, toast } from 'sonner';
import { App } from '@/App';
import { deadlineText, payText, placeText } from '@/lib/format';
import { axeViolations, mockApi, renderPage, studentUser } from '@/test/render';

const job = {
  id: 3,
  company: 'Acme',
  title: 'Backend Intern',
  description: 'Build APIs.',
  requirements: '',
  skills: ['Python', 'SQL'],
  location: 'Pune',
  remote: false,
  job_type: 'internship',
  stipend_min: 30000,
  stipend_max: 40000,
  duration_months: 6,
  deadline: '2031-01-01',
  apply_url: 'https://careers.example.com/3',
  status: 'indexed',
  published_at: null,
};

const breakdown = {
  score: 0.5,
  match_percent: 72,
  components: [
    {
      key: 'skills',
      label: 'Skills',
      value: 0.5,
      weight: 0.2,
      contribution: 0.1,
      note: '1 of 2 required skills',
    },
  ],
  matched_skills: ['Python'],
  missing_skills: ['SQL'],
  preference_checks: [{ key: 'location', label: 'Location: Pune', met: true }],
};

const hit = { job, score: 0.5, breakdown, saved: false, application_status: null };
const base = {
  'GET /auth/me': studentUser,
  'GET /notifications/unread': { unread: 2 },
  'GET /announcement': { id: null, message: null },
  'GET /saved-searches': [],
  'POST /search': {
    items: [hit],
    total: 1,
    page: 1,
    page_size: 12,
    personalized: true,
    weak_match: false,
  },
};

describe('student portal', () => {
  it('explains the match on a posting without hiding the formula', async () => {
    mockApi({
      ...base,
      'GET /jobs/3': { job, breakdown, saved: false, application: null, similar: [] },
    });
    const { container } = renderPage(<App />, '/jobs/3');
    expect(await screen.findByText('Why this fits')).toBeInTheDocument();
    expect(screen.getByText(/does not predict selection/)).toBeInTheDocument();
    expect(screen.getByText('Not in your profile: SQL.')).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it('saves optimistically and rolls back on failure', async () => {
    mockApi({
      ...base,
      'PUT /saved/3': Response.json(
        { error: { code: 'server_error', message: 'Please try again.' } },
        { status: 500 },
      ),
    });
    renderPage(<App />, '/jobs');
    const button = await screen.findByRole('button', { name: 'Save: Backend Intern' });
    await userEvent.click(button);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Save: Backend Intern' })).toHaveAttribute(
        'aria-pressed',
        'false',
      ),
    );
  });

  it('sends filters from the address bar and shows them as chips', async () => {
    const calls = mockApi(base);
    const { container } = renderPage(<App />, '/jobs?q=python&type=internship&loc=Pune');
    expect(await screen.findByRole('link', { name: 'Backend Intern' })).toBeInTheDocument();
    const body = calls.find((c) => c.key === 'POST /search')?.body as Record<string, unknown>;
    expect(body).toMatchObject({
      query: 'python',
      filters: { job_type: 'internship', locations: ['Pune'] },
    });
    expect(screen.getAllByRole('button', { name: /Remove filter/ })).toHaveLength(2);
    expect(await axeViolations(container)).toEqual([]);
  });

  it('offers a next step when nothing matches', async () => {
    mockApi({
      ...base,
      'POST /search': {
        items: [],
        total: 0,
        page: 1,
        page_size: 12,
        personalized: false,
        weak_match: false,
      },
    });
    renderPage(<App />, '/jobs?remote=1');
    expect(await screen.findByText('No postings match')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove all filters' })).toBeInTheDocument();
  });

  it('has a list alternative to dragging', async () => {
    const calls = mockApi({
      ...base,
      'GET /applications': [
        { id: 1, status: 'applied', notes: '', updated_at: '2031-01-01T00:00:00Z', job },
      ],
      'PUT /applications/3': {},
    });
    const { container } = renderPage(<App />, '/applications');
    await userEvent.click(await screen.findByRole('button', { name: 'List' }));
    screen.getByRole('combobox', { name: 'Stage for Backend Intern' }).focus();
    await userEvent.keyboard('{Enter}');
    await userEvent.click(await screen.findByRole('option', { name: 'Interview' }));
    await waitFor(() =>
      expect(calls.find((c) => c.key === 'PUT /applications/3')?.body).toMatchObject({
        status: 'interview',
      }),
    );
    expect(await axeViolations(container)).toEqual([]);
  });

  it('undoes a stage change from the toast', async () => {
    // Toasts live in a module-level store; clear the ones earlier tests left behind.
    toast.dismiss();
    const calls = mockApi({
      ...base,
      'GET /applications': [
        { id: 1, status: 'applied', notes: '', updated_at: '2031-01-01T00:00:00Z', job },
      ],
      'PUT /applications/3': {},
    });
    renderPage(
      <>
        <Toaster />
        <App />
      </>,
      '/applications',
    );
    await userEvent.click(await screen.findByRole('button', { name: 'List' }));
    screen.getByRole('combobox', { name: 'Stage for Backend Intern' }).focus();
    await userEvent.keyboard('{Enter}');
    await userEvent.click(await screen.findByRole('option', { name: 'Interview' }));
    expect(await screen.findByText('Moved to Interview')).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: 'Undo' }));
    await waitFor(() => {
      const puts = calls.filter((c) => c.key === 'PUT /applications/3');
      expect(puts.map((c) => (c.body as { status: string }).status)).toEqual([
        'interview',
        'applied',
      ]);
    });
  });

  it('asks for more or fewer postings like this one, and undoes on a second press', async () => {
    const calls = mockApi({
      ...base,
      'GET /jobs/3': {
        job,
        breakdown,
        saved: false,
        application: null,
        similar: [],
        reaction: null,
      },
      'PUT /jobs/3/reaction': { reaction: 'up' },
    });
    renderPage(<App />, '/jobs/3');
    const more = await screen.findByRole('button', { name: 'More like this' });
    expect(more).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(more);
    await waitFor(() => expect(more).toHaveAttribute('aria-pressed', 'true'));
    expect(calls.find((c) => c.key === 'PUT /jobs/3/reaction')?.body).toEqual({ reaction: 'up' });
  });

  it('downloads deadlines and makes a private calendar link once', async () => {
    const calls = mockApi({
      ...base,
      'GET /applications': [],
      'GET /calendar/feed': { active: false, created_at: null },
      'POST /calendar/feed': {
        active: true,
        created_at: '2031-01-01T00:00:00Z',
        url: 'https://example.test/api/calendar/feed/secret.ics',
      },
    });
    const { container } = renderPage(<App />, '/applications');
    expect(await screen.findByRole('link', { name: /Download .ics file/ })).toHaveAttribute(
      'href',
      '/api/calendar/deadlines.ics',
    );
    await userEvent.click(screen.getByRole('button', { name: /Make a subscription link/ }));
    expect(await screen.findByRole('textbox', { name: 'Subscription link' })).toHaveValue(
      'https://example.test/api/calendar/feed/secret.ics',
    );
    expect(calls.some((c) => c.key === 'POST /calendar/feed')).toBe(true);
    expect(screen.getByRole('button', { name: 'Turn off the link' })).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it('formats pay, place and deadlines in plain words', () => {
    const now = new Date(2031, 0, 1);
    expect(deadlineText('2031-01-01', now)).toBe('Closes today');
    expect(deadlineText('2031-01-06', now)).toBe('Closes in 5 days');
    expect(deadlineText('2030-12-31', now)).toBe('Closed');
    expect(payText({ job_type: 'full-time', stipend_min: 1200000, stipend_max: 1800000 })).toBe(
      '₹12 lakh to ₹18 lakh a year',
    );
    expect(placeText({ location: '', remote: true })).toBe('Remote');
  });
});
