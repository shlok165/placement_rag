import { Compass, ShieldAlert } from 'lucide-react';
import { Link } from 'react-router';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/display';
import { useTitle } from '@/lib/title';

const back = (
  <Button asChild>
    <Link to="/">Go to home</Link>
  </Button>
);

export function ForbiddenPage() {
  useTitle('No access');
  return (
    <main className="mx-auto w-full max-w-xl px-4 py-16">
      <h1 className="sr-only">No access</h1>
      <EmptyState
        icon={ShieldAlert}
        title="403: This area is for CAPS coordinators only"
        action={back}
      >
        Your account is a student account. If you are part of the CAPS team, ask a coordinator for
        an invite.
      </EmptyState>
    </main>
  );
}

export function NotFoundPage() {
  useTitle('Page not found');
  return (
    <div className="mx-auto w-full max-w-xl px-4 py-16">
      <h1 className="sr-only">Page not found</h1>
      <EmptyState icon={Compass} title="We could not find that page" action={back}>
        The link may be old, or the posting may have been removed.
      </EmptyState>
    </div>
  );
}
