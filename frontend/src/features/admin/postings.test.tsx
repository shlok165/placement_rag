import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { emptyJob, localProblems } from './JobForm';
import { App } from '@/App';
import { axeViolations, coordinatorUser, mockApi, renderPage } from '@/test/render';

const row = {
  id: 7,
  company: 'Acme',
  title: 'Backend Intern',
  location: 'Pune',
  job_type: 'internship',
  deadline: '2031-01-01',
  status: 'failed',
  source: 'form',
  last_error: 'The file could not be read.',
  duplicate_of_id: null,
  needs_review: false,
  updated_at: '2031-01-01T00:00:00Z',
};

const base = {
  'GET /auth/me': coordinatorUser,
  'GET /admin/jobs': { items: [row], total: 1, page: 1, page_size: 20 },
  'GET /admin/jobs/companies': ['Acme'],
  'GET /admin/jobs/similar': [],
};

describe('postings', () => {
  it('lists postings with errors and bulk retry', async () => {
    const calls = mockApi({ ...base, 'POST /admin/jobs/bulk': { done: 1, skipped: 0 } });
    const { container } = renderPage(<App />, '/admin/postings');
    expect((await screen.findAllByText('The file could not be read.')).length).toBeGreaterThan(0);
    expect(await axeViolations(container)).toEqual([]);
    await userEvent.click(screen.getAllByLabelText('Select Backend Intern')[0]);
    await userEvent.click(screen.getByRole('button', { name: 'Retry failed' }));
    await waitFor(() =>
      expect(calls.find((c) => c.key === 'POST /admin/jobs/bulk')?.body).toEqual({
        ids: [7],
        action: 'retry',
      }),
    );
  });

  it('blocks publishing an empty form and says why', async () => {
    const calls = mockApi(base);
    const { container } = renderPage(<App />, '/admin/postings/new');
    await userEvent.click(await screen.findByRole('button', { name: 'Publish' }));
    expect(screen.getByText('Add a company.')).toBeInTheDocument();
    expect(calls.some((c) => c.key === 'POST /admin/jobs')).toBe(false);
    expect(await axeViolations(container)).toEqual([]);
  });

  it('checks pay order and deadline locally', () => {
    const problems = localProblems({
      ...emptyJob,
      stipend_min: 10,
      stipend_max: 5,
      deadline: '2020-01-01',
      apply_url: 'careers',
    });
    expect(Object.keys(problems)).toEqual(
      expect.arrayContaining(['stipend_max', 'deadline', 'apply_url']),
    );
  });
});
