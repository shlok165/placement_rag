import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { ConsentCard } from './ConsentCard';
import { ParsedProfileForm, PreferencesForm, ResumeUpload, useSaveProfile } from './ProfileForms';
import { Logo } from '@/components/Logo';
import { QueryState } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { Card, Progress } from '@/components/ui/display';
import { api } from '@/lib/api';
import { useUser, type User } from '@/lib/auth';
import { useTitle } from '@/lib/title';
import type { ParsedProfile, Preferences, Profile } from '@/lib/types';

const steps = [
  {
    title: 'Upload your resume',
    text: 'We read your skills and projects from it. Personal identifiers are removed first.',
  },
  { title: 'Check your profile', text: 'Fix anything that was read wrong or is missing.' },
  { title: 'Set your preferences', text: 'These decide how postings are ranked for you.' },
];

function Wizard({ initial }: { initial: Profile }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const { data: user } = useUser();
  const { data: profile = initial } = useQuery({
    queryKey: ['profile'],
    queryFn: () => api<Profile>('/profile'),
    initialData: initial,
  });
  const save = useSaveProfile();
  const [step, setStep] = useState(0);
  const [parsed, setParsed] = useState<ParsedProfile>(initial.parsed_profile);
  const [preferences, setPreferences] = useState<Preferences>(initial.preferences);

  const finish = useMutation({
    mutationFn: () => api<User>('/profile/onboarded', { method: 'POST' }),
    onSuccess: (updated) => {
      client.setQueryData(['me'], updated);
      client.invalidateQueries({ queryKey: ['home'] });
      navigate('/', { replace: true });
    },
  });

  const next = async () => {
    if (step === 1) await save.profile.mutateAsync(parsed);
    if (step === 2) {
      await save.preferences.mutateAsync(preferences);
      finish.mutate();
      return;
    }
    setStep(step + 1);
  };
  const skip = () => (step === 2 ? finish.mutate() : setStep(step + 1));
  const busy = save.profile.isPending || save.preferences.isPending || finish.isPending;
  const current = steps[step];

  return (
    <Card className="p-5 sm:p-8">
      <p className="text-muted-foreground text-sm" aria-live="polite">
        Step {step + 1} of {steps.length}
      </p>
      <div className="mt-2">
        <Progress value={((step + 1) / steps.length) * 100} label="Onboarding progress" />
      </div>
      <h1 className="mt-5 text-2xl font-semibold">{current.title}</h1>
      <p className="text-muted-foreground mt-1">{current.text}</p>
      <div className="mt-6">
        {step === 0 && (
          <div className="flex flex-col gap-6">
            {!user?.consent_at && <ConsentCard />}
            <ResumeUpload profile={profile} onParsed={(r) => setParsed(r.parsed_profile)} />
          </div>
        )}
        {step === 1 && <ParsedProfileForm value={parsed} onChange={setParsed} />}
        {step === 2 && <PreferencesForm value={preferences} onChange={setPreferences} />}
      </div>
      <div className="mt-8 flex flex-wrap items-center gap-2">
        <Button onClick={next} loading={busy}>
          {step === 2 ? 'Save and finish' : step === 1 ? 'Save and continue' : 'Continue'}
        </Button>
        {step > 0 && (
          <Button variant="secondary" onClick={() => setStep(step - 1)}>
            Back
          </Button>
        )}
        <Button variant="ghost" onClick={skip} disabled={busy}>
          Skip this step
        </Button>
      </div>
    </Card>
  );
}

export function OnboardingPage() {
  useTitle('Get started');
  const query = useQuery({ queryKey: ['profile'], queryFn: () => api<Profile>('/profile') });
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-3xl flex-col gap-6 px-4 py-8">
      <Logo />
      <QueryState query={query}>{(profile) => <Wizard initial={profile} />}</QueryState>
    </main>
  );
}
