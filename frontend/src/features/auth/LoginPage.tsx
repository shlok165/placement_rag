import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router';
import { AuthLayout } from './AuthLayout';
import { GoogleButton, googleError } from './GoogleButton';
import { Button } from '@/components/ui/button';
import { Alert } from '@/components/ui/display';
import { Field, Input } from '@/components/ui/form';
import { messageOf } from '@/lib/api';
import { homePath, useDemoAvailable, useDemoLogin, useLogin, useUser } from '@/lib/auth';

export function LoginPage() {
  const { data: user } = useUser();
  const login = useLogin();
  const demo = useDemoLogin();
  const { data: demoAvailable } = useDemoAvailable();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const next = params.get('next');
  const safeNext = next?.startsWith('/') && !next.startsWith('//') ? next : null;

  if (user && !login.isPending && !demo.isPending)
    return <Navigate to={safeNext ?? homePath(user)} replace />;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate(
      { email, password },
      { onSuccess: (signedIn) => navigate(safeNext ?? homePath(signedIn), { replace: true }) },
    );
  };

  return (
    <AuthLayout
      title="Sign in"
      description="Welcome back. Use your institute email."
      footer={
        <>
          New here?{' '}
          <Link className="text-primary font-medium underline underline-offset-4" to="/register">
            Create a student account
          </Link>
        </>
      }
    >
      <div className="mb-4">
        <GoogleButton error={googleError(params.get('error'))} />
      </div>
      <form onSubmit={submit} className="flex flex-col gap-4">
        {login.isError && <Alert tone="danger">{messageOf(login.error)}</Alert>}
        <Field label="Institute email">
          {(ids) => (
            <Input
              {...ids}
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          )}
        </Field>
        <Field label="Password">
          {(ids) => (
            <Input
              {...ids}
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </Field>
        <Button type="submit" loading={login.isPending}>
          Sign in
        </Button>
      </form>
      {demoAvailable && (
        <div className="mt-6">
          <div className="text-muted-foreground flex items-center gap-3 text-xs">
            <span className="bg-border h-px flex-1" />
            or
            <span className="bg-border h-px flex-1" />
          </div>
          {demo.isError && (
            <Alert tone="danger" className="mt-4">
              {messageOf(demo.error)}
            </Alert>
          )}
          <Button
            variant="secondary"
            className="mt-4 w-full"
            loading={demo.isPending}
            onClick={() =>
              demo.mutate(undefined, {
                onSuccess: (signedIn) => navigate(homePath(signedIn), { replace: true }),
              })
            }
          >
            Explore with the demo account
          </Button>
          <p className="text-muted-foreground mt-2 text-center text-xs">
            A shared student account with sample postings. No sign-up needed.
          </p>
        </div>
      )}
    </AuthLayout>
  );
}
