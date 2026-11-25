import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '@/App';
import { axeViolations, coordinatorUser, mockApi, renderPage, studentUser } from '@/test/render';

const signedOut = () =>
  Response.json({ error: { code: 'unauthenticated', message: 'Sign in' } }, { status: 401 });

describe('auth', () => {
  it('shows an accessible login page to visitors', async () => {
    mockApi({ 'GET /auth/me': signedOut() });
    const { container } = renderPage(<App />, '/applications');
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it('explains a failed sign in', async () => {
    mockApi({
      'GET /auth/me': signedOut(),
      'POST /auth/login': Response.json(
        { error: { code: 'bad_credentials', message: 'That email and password do not match.' } },
        { status: 401 },
      ),
    });
    renderPage(<App />, '/login');
    await userEvent.type(await screen.findByLabelText('Institute email'), 'a@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'wrong');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('do not match');
  });

  it('gives students a clear 403 page on admin routes', async () => {
    mockApi({ 'GET /auth/me': studentUser });
    renderPage(<App />, '/admin/team');
    expect(await screen.findByText(/CAPS coordinators only/)).toBeInTheDocument();
  });

  it('lets coordinators open the admin portal', async () => {
    mockApi({
      'GET /auth/me': coordinatorUser,
      'GET /admin/team': [coordinatorUser],
      'GET /admin/team/invites': [],
    });
    renderPage(<App />, '/admin/team');
    expect(await screen.findByRole('heading', { name: 'Team' })).toBeInTheDocument();
  });

  it('checks the password before sending the form', async () => {
    const calls = mockApi({ 'GET /auth/me': signedOut() });
    const { container } = renderPage(<App />, '/register');
    await userEvent.type(await screen.findByLabelText('Full name'), 'New Student');
    await userEvent.type(screen.getByLabelText('Institute email'), 'n@iitrpr.ac.in');
    await userEvent.type(screen.getByLabelText('Password'), 'short');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('5 more characters'));
    expect(calls.some((c) => c.key.startsWith('POST'))).toBe(false);
    expect(await axeViolations(container)).toEqual([]);
  });
});
