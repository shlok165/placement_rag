import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { toast } from 'sonner';
import { ConsentCard, useConsent } from './ConsentCard';
import { ParsedProfileForm, PreferencesForm, ResumeUpload, useSaveProfile } from './ProfileForms';
import { QueryState } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import {
  Alert,
  Card,
  PageHeader,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/display';
import { Field, Input } from '@/components/ui/form';
import { Dialog } from '@/components/ui/overlay';
import { api, messageOf } from '@/lib/api';
import { useUser } from '@/lib/auth';
import { formatDate } from '@/lib/format';
import { useTitle } from '@/lib/title';
import type { Profile } from '@/lib/types';

function SaveBar({
  dirty,
  busy,
  onSave,
  onReset,
}: {
  dirty: boolean;
  busy: boolean;
  onSave: () => void;
  onReset: () => void;
}) {
  return (
    <div className="mt-6 flex flex-wrap items-center gap-2 border-t pt-4">
      <Button
        onClick={onSave}
        disabled={!dirty}
        title={dirty ? undefined : 'Nothing to save yet'}
        loading={busy}
      >
        Save changes
      </Button>
      {dirty && (
        <Button variant="ghost" onClick={onReset}>
          Discard
        </Button>
      )}
      <span className="text-muted-foreground text-sm" aria-live="polite">
        {dirty ? 'Unsaved changes' : 'All changes saved'}
      </span>
    </div>
  );
}

function ProfileTabs({ profile }: { profile: Profile }) {
  const save = useSaveProfile();
  const [parsed, setParsed] = useState(profile.parsed_profile);
  const [preferences, setPreferences] = useState(profile.preferences);
  const changed = (a: unknown, b: unknown) => JSON.stringify(a) !== JSON.stringify(b);

  return (
    <>
      <TabsContent value="profile" className="mt-4 flex flex-col gap-6">
        <Card className="p-5">
          <h2 className="mb-4 font-semibold">Resume</h2>
          <ResumeUpload profile={profile} onParsed={(r) => setParsed(r.parsed_profile)} />
        </Card>
        <Card className="p-5">
          <h2 className="mb-4 font-semibold">Profile</h2>
          <ParsedProfileForm value={parsed} onChange={setParsed} />
          <SaveBar
            dirty={changed(parsed, profile.parsed_profile)}
            busy={save.profile.isPending}
            onReset={() => setParsed(profile.parsed_profile)}
            onSave={() =>
              save.profile.mutate(parsed, {
                onSuccess: (updated) => {
                  setParsed(updated.parsed_profile);
                  toast.success('Profile saved');
                },
              })
            }
          />
        </Card>
      </TabsContent>
      <TabsContent value="preferences" className="mt-4">
        <Card className="p-5">
          <h2 className="mb-4 font-semibold">Preferences</h2>
          <PreferencesForm value={preferences} onChange={setPreferences} />
          <SaveBar
            dirty={changed(preferences, profile.preferences)}
            busy={save.preferences.isPending}
            onReset={() => setPreferences(profile.preferences)}
            onSave={() =>
              save.preferences.mutate(preferences, {
                onSuccess: (updated) => {
                  setPreferences(updated.preferences);
                  toast.success('Preferences saved');
                },
              })
            }
          />
        </Card>
      </TabsContent>
    </>
  );
}

function PrivacyTab() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const { data: user } = useUser();
  const consent = useConsent();
  const [deleting, setDeleting] = useState(false);
  const [password, setPassword] = useState('');
  const remove = useMutation({
    mutationFn: () => api<void>('/profile/delete-account', { method: 'POST', body: { password } }),
    onSuccess: () => {
      client.clear();
      client.setQueryData(['me'], null);
      navigate('/login', { replace: true });
      toast.success('Your account and data were deleted');
    },
  });

  return (
    <TabsContent value="privacy" className="mt-4 flex flex-col gap-6">
      {user?.consent_at ? (
        <Card className="p-5">
          <h2 className="font-semibold">AI features are on</h2>
          <p className="text-muted-foreground mt-1 text-sm">
            You agreed on {formatDate(user.consent_at)}. Redacted resume text and copilot messages
            may be sent to a third-party AI provider.{' '}
            <Link to="/privacy" className="text-primary underline underline-offset-4">
              Privacy notice
            </Link>
          </p>
          <Button
            variant="secondary"
            className="mt-4"
            loading={consent.isPending}
            onClick={() =>
              consent.mutate(false, { onSuccess: () => toast.success('AI features turned off') })
            }
          >
            Turn off AI features
          </Button>
        </Card>
      ) : (
        <ConsentCard />
      )}
      <Card className="p-5">
        <h2 className="font-semibold">What the copilot remembers</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          See, edit or delete every fact the copilot keeps about you.
        </p>
        <Button asChild variant="secondary" className="mt-4">
          <Link to="/memory">Open memory</Link>
        </Button>
      </Card>
      <Card className="p-5">
        <h2 className="font-semibold">Download my data</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          A JSON file with your profile, applications, conversations and memory.
        </p>
        <Button asChild variant="secondary" className="mt-4">
          <a href="/api/profile/export" download>
            <Download aria-hidden />
            Download
          </a>
        </Button>
      </Card>
      <Card className="border-destructive/40 p-5">
        <h2 className="font-semibold">Delete my account</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          Removes your profile, resume file, applications, conversations, memory and notifications.
          This cannot be undone.
        </p>
        <Button variant="destructive" className="mt-4" onClick={() => setDeleting(true)}>
          Delete my account
        </Button>
      </Card>
      <Dialog
        open={deleting}
        onOpenChange={(open) => {
          setDeleting(open);
          setPassword('');
          remove.reset();
        }}
        title="Delete your account and all data?"
        description="This cannot be undone. Enter your password to confirm."
      >
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            remove.mutate();
          }}
        >
          {remove.isError && <Alert tone="danger">{messageOf(remove.error)}</Alert>}
          <Field label="Password">
            {(ids) => (
              <Input
                {...ids}
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            )}
          </Field>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="secondary" onClick={() => setDeleting(false)}>
              Keep my account
            </Button>
            <Button type="submit" variant="destructive" loading={remove.isPending}>
              Delete everything
            </Button>
          </div>
        </form>
      </Dialog>
    </TabsContent>
  );
}

export function AccountPage() {
  useTitle('Profile and privacy');
  const [params, setParams] = useSearchParams();
  const query = useQuery({ queryKey: ['profile'], queryFn: () => api<Profile>('/profile') });
  return (
    <>
      <PageHeader title="Profile and privacy" />
      <Tabs
        value={params.get('tab') ?? 'profile'}
        onValueChange={(tab) => setParams({ tab }, { replace: true })}
      >
        <TabsList aria-label="Sections">
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="preferences">Preferences</TabsTrigger>
          <TabsTrigger value="privacy">Privacy and data</TabsTrigger>
        </TabsList>
        <QueryState query={query}>{(profile) => <ProfileTabs profile={profile} />}</QueryState>
        <PrivacyTab />
      </Tabs>
    </>
  );
}
