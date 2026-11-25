import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { CheckRow } from '@/components/ui/form';
import { api, messageOf } from '@/lib/api';
import type { User } from '@/lib/auth';

export function useConsent() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (agreed: boolean) =>
      api<User>('/profile/consent', { method: 'POST', body: { agreed } }),
    onSuccess: (user) => client.setQueryData(['me'], user),
    onError: (error) => toast.error(messageOf(error)),
  });
}

export function ConsentCard({ reason }: { reason?: string }) {
  const [agreed, setAgreed] = useState(false);
  const consent = useConsent();
  return (
    <section aria-labelledby="consent-title" className="bg-muted rounded-lg border p-4 sm:p-5">
      <h2 id="consent-title" className="flex items-center gap-2 font-semibold">
        <ShieldCheck className="text-primary size-5" aria-hidden />
        How AI features use your data
      </h2>
      {reason && <p className="mt-2 text-sm">{reason}</p>}
      <ul className="mt-3 flex list-disc flex-col gap-1.5 pl-5 text-sm">
        <li>
          Phone numbers, emails, addresses, links and ID numbers are removed from your resume first.
        </li>
        <li>
          The remaining text, and what you type to the copilot, may be sent to a third-party AI
          provider.
        </li>
        <li>You can withdraw at any time. Search and matching work without this.</li>
      </ul>
      <div className="mt-3">
        <CheckRow
          label="I agree to this use of my data"
          checked={agreed}
          onCheckedChange={setAgreed}
        />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button
          size="sm"
          disabled={!agreed}
          title={agreed ? undefined : 'Tick the box to agree'}
          loading={consent.isPending}
          onClick={() => consent.mutate(true)}
        >
          Turn on AI features
        </Button>
        <Link to="/privacy" className="text-primary text-sm underline underline-offset-4">
          Read the privacy notice
        </Link>
      </div>
    </section>
  );
}
