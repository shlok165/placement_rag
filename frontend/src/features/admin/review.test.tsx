import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '@/App';
import { axeViolations, coordinatorUser, mockApi, renderPage } from '@/test/render';

const parsed = {
  id: 7,
  company: 'Acme',
  title: 'Backend Intern',
  description: 'Build APIs for the payments team.',
  requirements: 'Open to pre-final year students.',
  skills: ['Python', 'SQL'],
  location: 'Pune',
  remote: false,
  job_type: 'internship',
  stipend_min: 30000,
  stipend_max: 40000,
  duration_months: 3,
  deadline: '2031-01-01',
  apply_url: 'https://careers.example.com/7',
  status: 'draft',
  published_at: null,
  source: 'paste',
  raw_text: 'Backend Intern at Acme. Pune. Stipend 30k to 40k. Apply by 1 Jan 2031.',
  parse_meta: {
    confidence: { title: 'high', stipend_min: 'low', deadline: 'medium' },
    low_confidence: ['stipend_min'],
    parsed_by: 'mock',
    needs_review: true,
  },
  auto_publish: false,
  last_error: null,
  duplicate_of_id: null,
  created_at: '2031-01-01T00:00:00Z',
  updated_at: '2031-01-01T00:00:00Z',
  indexed: false,
  file_name: null,
  duplicates: [
    {
      id: 3,
      company: 'Acme',
      title: 'Backend Intern',
      deadline: '2031-01-01',
      status: 'indexed',
      similarity: 0.97,
    },
  ],
};

const base = {
  'GET /auth/me': coordinatorUser,
  'GET /admin/jobs/7': parsed,
  'GET /admin/jobs/7/history': [],
  'GET /admin/jobs/companies': ['Acme'],
  'GET /admin/jobs/similar': [],
};

describe('reviewing a parsed posting', () => {
  it('shows the original beside the fields, flags doubtful ones and publishes', async () => {
    const calls = mockApi({
      ...base,
      'POST /admin/jobs/7/publish': { ...parsed, status: 'pending' },
    });
    const { container } = renderPage(<App />, '/admin/postings/7');
    expect(await screen.findByText('Review before publishing')).toBeVisible();
    expect(screen.getByRole('region', { name: 'Original text' })).toHaveTextContent(
      'Stipend 30k to 40k',
    );
    expect(screen.getByText(/possible duplicate|already/i)).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
    await userEvent.click(screen.getByRole('button', { name: 'Publish' }));
    await waitFor(() =>
      expect(calls.some((c) => c.key === 'POST /admin/jobs/7/publish')).toBe(true),
    );
  });
});
