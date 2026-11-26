import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '@/App';
import { axeViolations, coordinatorUser, mockApi, renderPage } from '@/test/render';

const row = {
  message_id: 42,
  created_at: '2031-01-01T00:00:00Z',
  source: 'shared',
  rating: 'down',
  question: 'Find backend internships in Pune',
  answer_kind: 'repaired',
  tools: 1,
  latency_ms: 2300,
};

const trace = {
  ...row,
  comment: 'wrong city',
  answer: 'Try [#3].',
  citations: [{ job_id: 3, title: 'Backend Intern', company: 'Acme' }],
  tools: [
    {
      name: 'search_jobs',
      arguments: { query: 'backend', filters: { locations: ['Pune'] } },
      ok: true,
      summary: '5 results',
      ms: 41,
    },
  ],
  checks: {
    answer_kind: 'repaired',
    structured: true,
    format_repairs: 1,
    fabrications_caught: 0,
    notice: null,
    draft: false,
  },
  mode: 'live',
  iterations: 3,
  tokens: 4200,
  cache_hits: 1,
};

describe('agent traces', () => {
  it('lists shared turns and shows the steps of one', async () => {
    mockApi({
      'GET /auth/me': coordinatorUser,
      'GET /admin/traces': [row],
      'GET /admin/traces/42': trace,
    });
    const { container } = renderPage(<App />, '/admin/traces');
    const link = await screen.findByRole('link', { name: 'Find backend internships in Pune' });
    expect(screen.getByText('Structured after a repair')).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
    await userEvent.click(link);
    expect(await screen.findByText('search_jobs')).toBeVisible();
    expect(screen.getByText('Shared by a student')).toBeVisible();
    expect(screen.getByText(/wrong city/)).toBeVisible();
    expect(screen.getByText('41 ms')).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });
});
