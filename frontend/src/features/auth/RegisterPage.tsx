import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { AuthLayout } from './AuthLayout';
import { Button } from '@/components/ui/button';
import { Alert } from '@/components/ui/display';
import { Field, Input } from '@/components/ui/form';
import { api, ApiError, messageOf } from '@/lib/api';
import type { User } from '@/lib/auth';

const PASSWORD_HINT = 'At least 10 characters, mixing letters with numbers or symbols.';

function passwordProblem(password: string): string | null {
  if (!password) return null;
  if (password.length < 10) return `${10 - password.length} more characters needed.`;
  if (/^[a-z]+$/i.test(password) || /^\d+$/.test(password))
    return 'Mix letters with numbers or symbols.';
  return null;
}

function AccountForm({ invite }: { invite?: string }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: '', email: '', password: '' });
  const [touched, setTouched] = useState(false);

  const submit = useMutation({
    mutationFn: () =>
      invite
        ? api<User>('/auth/accept-invite', {
            method: 'POST',
            body: { token: invite, full_name: form.full_name, password: form.password },
          })
        : api<User>('/auth/register', { method: 'POST', body: form }),
    onSuccess: (user) => {
      client.setQueryData(['me'], user);
      navigate(invite ? '/admin' : '/onboarding', { replace: true });
    },
  });

  const error = submit.error instanceof ApiError ? submit.error : null;
  const set = (key: keyof typeof form) => (event: { target: { value: string } }) =>
    setForm({ ...form, [key]: event.target.value });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (!passwordProblem(form.password)) submit.mutate();
  };

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      {submit.isError && <Alert tone="danger">{messageOf(submit.error)}</Alert>}
      <Field label="Full name" error={error?.fieldError('full_name')}>
        {(ids) => (
          <Input
            {...ids}
            autoComplete="name"
            required
            minLength={2}
            value={form.full_name}
            onChange={set('full_name')}
          />
        )}
      </Field>
      {!invite && (
        <Field
          label="Institute email"
          hint="Your iitrpr.ac.in address."
          error={error?.fieldError('email')}
        >
          {(ids) => (
            <Input
              {...ids}
              type="email"
              autoComplete="username"
              required
              value={form.email}
              onChange={set('email')}
            />
          )}
        </Field>
      )}
      <Field
        label="Password"
        hint={PASSWORD_HINT}
        error={(touched && passwordProblem(form.password)) || error?.fieldError('password')}
      >
        {(ids) => (
          <Input
            {...ids}
            type="password"
            autoComplete="new-password"
            required
            value={form.password}
            onChange={set('password')}
            onBlur={() => setTouched(true)}
          />
        )}
      </Field>
      <Button type="submit" loading={submit.isPending}>
        Create account
      </Button>
    </form>
  );
}

const signIn = (
  <>
    Already have an account?{' '}
    <Link className="text-primary font-medium underline underline-offset-4" to="/login">
      Sign in
    </Link>
  </>
);

export function RegisterPage() {
  return (
    <AuthLayout title="Create a student account" footer={signIn}>
      <AccountForm />
    </AuthLayout>
  );
}

export function AcceptInvitePage() {
  const token = useLocation().hash.slice(1);
  return (
    <AuthLayout
      title="Join as a coordinator"
      description="Set your name and password to accept the invite."
      footer={signIn}
    >
      {token ? (
        <AccountForm invite={token} />
      ) : (
        <Alert tone="danger" title="This invite link is incomplete">
          Open the full link you were sent, or ask a coordinator for a new one.
        </Alert>
      )}
    </AuthLayout>
  );
}
