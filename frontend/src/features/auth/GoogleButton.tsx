import { Alert } from '@/components/ui/display';
import { useSignInOptions } from '@/lib/auth';

const errors: Record<string, string> = {
  google_domain: 'Use your IIT Ropar Google account. Other Google accounts cannot sign in here.',
  google_unverified: 'Google has not verified that email address yet.',
  google_state: 'That sign-in link expired or was opened twice. Please try again.',
  google_failed: 'Google sign-in did not finish. Please try again in a minute.',
  google_off: 'Google sign-in is not set up on this server.',
  inactive: 'This account is inactive. Contact the CAPS office.',
};

export function googleError(code: string | null): string | null {
  return code ? (errors[code] ?? 'Sign-in did not finish. Please try again.') : null;
}

function GoogleMark() {
  return (
    <svg viewBox="0 0 18 18" className="size-[18px]" aria-hidden>
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18Z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72a5.41 5.41 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33Z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58Z"
      />
    </svg>
  );
}

/** A full-page link to the server, which hands over to Google. Hidden when not configured. */
export function GoogleButton({ error }: { error?: string | null }) {
  const { data } = useSignInOptions();
  if (!data?.google) return null;
  return (
    <div className="flex flex-col gap-4">
      {error && <Alert tone="danger">{error}</Alert>}
      <a
        href="/api/auth/google"
        className="bg-card hover:bg-muted focus-visible:ring-ring flex h-11 w-full items-center justify-center gap-3 rounded-md border text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none sm:h-10"
      >
        <GoogleMark />
        Continue with Google
      </a>
      <div className="text-muted-foreground flex items-center gap-3 text-xs">
        <span className="bg-border h-px flex-1" />
        or use your email
        <span className="bg-border h-px flex-1" />
      </div>
    </div>
  );
}
