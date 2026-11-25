import { Navigate, Outlet, useLocation } from 'react-router';
import { ForbiddenPage } from './ErrorPages';
import { Button } from '@/components/ui/button';
import { Alert, LoadingRows } from '@/components/ui/display';
import { messageOf } from '@/lib/api';
import { useUser } from '@/lib/auth';

function FullPageStatus() {
  const { error, refetch } = useUser();
  return (
    <main className="mx-auto w-full max-w-2xl p-6">
      {error ? (
        <Alert
          tone="danger"
          title="We could not load your account"
          action={
            <Button variant="secondary" size="sm" onClick={() => refetch()}>
              Try again
            </Button>
          }
        >
          {messageOf(error)}
        </Alert>
      ) : (
        <LoadingRows label="Loading your account" />
      )}
    </main>
  );
}

export function RequireUser() {
  const { data: user, isPending, isError } = useUser();
  const location = useLocation();
  if (isPending || isError) return <FullPageStatus />;
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={location.pathname === '/' ? '/login' : `/login?next=${next}`} replace />;
  }
  return <Outlet />;
}

export function RequireCoordinator() {
  const { data: user } = useUser();
  if (user?.role !== 'coordinator') return <ForbiddenPage />;
  return <Outlet />;
}
