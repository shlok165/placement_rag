import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '@/App';
import { axeViolations, mockApi, renderPage, studentUser } from '@/test/render';

const empty = {
  items: [],
  total: 0,
  page: 1,
  page_size: 12,
  personalized: true,
  weak_match: false,
};

const base = {
  'GET /auth/me': studentUser,
  'GET /notifications/unread': { unread: 0 },
  'GET /announcement': { id: null, message: null },
  'GET /saved-searches': [],
  'POST /search': empty,
  'POST /search/parse': {
    query: 'ML',
    filters: { remote: true, job_type: 'internship', locations: ['Bengaluru'] },
    chips: [
      { key: 'remote', label: 'Remote', value: 'True' },
      { key: 'job_type', label: 'Internship', value: 'internship' },
      { key: 'locations', label: 'Bengaluru', value: 'Bengaluru' },
    ],
  },
};

const searches = (calls: { key: string; body: unknown }[]) =>
  calls.filter((c) => c.key === 'POST /search').map((c) => c.body as Record<string, unknown>);

describe('filters from typed words', () => {
  it('shows chips before searching and applies only the ones kept', async () => {
    const calls = mockApi(base);
    const { container } = renderPage(<App />, '/jobs');
    const box = await screen.findByRole('searchbox', { name: 'Search postings' });
    await userEvent.type(box, 'remote ML internship in Bangalore{Enter}');
    expect(await screen.findByRole('heading', { name: 'Use these as filters?' })).toBeVisible();
    expect(screen.getByText('“ML”')).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
    const before = searches(calls).length;

    await userEvent.click(screen.getByRole('button', { name: 'Remove Remote' }));
    expect(screen.queryByRole('button', { name: 'Remove Remote' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Search with these filters' }));

    await waitFor(() => expect(searches(calls).length).toBeGreaterThan(before));
    const last = searches(calls).at(-1)!;
    expect(last.query).toBe('ML');
    expect(last.filters).toMatchObject({ job_type: 'internship', locations: ['Bengaluru'] });
    expect((last.filters as Record<string, unknown>).remote).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Use these as filters?' })).toBeNull();
  });

  it('can ignore the chips and search the words as typed', async () => {
    const calls = mockApi(base);
    renderPage(<App />, '/jobs');
    const box = await screen.findByRole('searchbox', { name: 'Search postings' });
    await userEvent.type(box, 'remote ML internship in Bangalore{Enter}');
    await userEvent.click(await screen.findByRole('button', { name: 'Search my words as typed' }));
    await waitFor(() =>
      expect(searches(calls).at(-1)?.query).toBe('remote ML internship in Bangalore'),
    );
  });

  it('searches at once when nothing looks like a filter', async () => {
    const calls = mockApi({
      ...base,
      'POST /search/parse': { query: 'robotics', filters: {}, chips: [] },
    });
    renderPage(<App />, '/jobs');
    const box = await screen.findByRole('searchbox', { name: 'Search postings' });
    await userEvent.type(box, 'robotics{Enter}');
    await waitFor(() => expect(searches(calls).at(-1)?.query).toBe('robotics'));
    expect(screen.queryByRole('heading', { name: 'Use these as filters?' })).toBeNull();
  });
});
