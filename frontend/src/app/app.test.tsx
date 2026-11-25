import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '@/App';
import { axeViolations, mockApi, renderPage, studentUser } from '@/test/render';

const base = {
  'GET /auth/me': studentUser,
  'GET /notifications/unread': { unread: 0 },
  'GET /announcement': { id: 1, message: 'Mock interviews on Friday' },
  'GET /home': {
    recommended: [],
    closing_soon: [],
    pipeline: {},
    unread: 0,
    profile_ready: false,
  },
  'POST /search': { items: [], total: 0, page: 1, page_size: 5 },
  'GET /saved-searches': [],
};

describe('app shell', () => {
  it('shows the tour once, can be skipped, and reopens from Help', async () => {
    mockApi(base);
    renderPage(<App />, '/', { tour: true });
    expect(await screen.findByText('Find postings in your own words')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Skip tour' }));
    expect(screen.queryByText('Find postings in your own words')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Help' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Open the tour' }));
    expect(screen.getByText('Find postings in your own words')).toBeInTheDocument();
  });

  it('opens the palette with the keyboard and goes to a page', async () => {
    mockApi(base);
    renderPage(<App />, '/');
    await screen.findByRole('heading', { name: 'Recommended for you' });
    await userEvent.keyboard('{Control>}k{/Control}');
    await userEvent.type(await screen.findByPlaceholderText('Type a page or a posting'), 'help');
    await userEvent.keyboard('{Enter}');
    expect(await screen.findByRole('heading', { name: 'Help', level: 1 })).toBeInTheDocument();
  });

  it('moves to the search box with a slash', async () => {
    mockApi(base);
    renderPage(<App />, '/jobs');
    const box = await screen.findByRole('searchbox');
    await userEvent.keyboard('/');
    expect(box).toHaveFocus();
    await userEvent.keyboard('a/b');
    expect(box).toHaveValue('a/b');
  });

  it('shows the announcement and lets the student hide it', async () => {
    mockApi(base);
    const { container } = renderPage(<App />, '/');
    expect(await screen.findByText('Mock interviews on Friday')).toBeInTheDocument();
    await screen.findByRole('heading', { name: 'Recommended for you' });
    expect(await axeViolations(container)).toEqual([]);
    await userEvent.click(screen.getByRole('button', { name: 'Hide announcement' }));
    expect(screen.queryByText('Mock interviews on Friday')).not.toBeInTheDocument();
  });

  it('collects feedback with the page it came from', async () => {
    const calls = mockApi({ ...base, 'POST /feedback': { received: true } });
    renderPage(<App />, '/help');
    await userEvent.click(await screen.findByRole('button', { name: 'Give feedback' }));
    await userEvent.type(screen.getByLabelText('Message'), 'Clear and quick');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() =>
      expect(calls.find((c) => c.key === 'POST /feedback')?.body).toMatchObject({
        message: 'Clear and quick',
        page: '/help',
      }),
    );
  });

  it('asks for every answer in the usability survey', async () => {
    const calls = mockApi({ ...base, 'POST /sus': { score: 75 } });
    const { container } = renderPage(<App />, '/survey');
    await userEvent.click(await screen.findByRole('button', { name: 'Send answers' }));
    expect(screen.getByText('Choose one option.')).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
    for (const option of screen.getAllByRole('radio', { name: 'Agree' }))
      await userEvent.click(option);
    await userEvent.click(screen.getByRole('button', { name: 'Send answers' }));
    expect(await screen.findByText(/score for the portal is 75/)).toBeInTheDocument();
    expect(calls.find((c) => c.key === 'POST /sus')?.body).toMatchObject({
      answers: Array(10).fill(4),
    });
  });
});
