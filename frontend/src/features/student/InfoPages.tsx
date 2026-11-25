import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { Card, PageHeader } from '@/components/ui/display';
import { useTitle } from '@/lib/title';

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-6 first:mt-0">
      <h2 className="font-semibold">{title}</h2>
      <div className="mt-2 flex max-w-prose flex-col gap-2 text-sm leading-relaxed">{children}</div>
    </section>
  );
}

export function PrivacyPage() {
  useTitle('Privacy notice');
  return (
    <>
      <PageHeader title="Privacy notice" />
      <Card className="p-5 sm:p-8">
        <Section title="What is stored">
          <p>
            Your account, the resume file you upload, the redacted text taken from it, your profile,
            preferences, saved postings, applications, conversations with the copilot and the facts
            you allow it to remember.
          </p>
        </Section>
        <Section title="What is removed first">
          <p>
            Before resume text is stored or processed, we remove emails, phone numbers, addresses,
            links, dates of birth, names we know and ID-like numbers. You can see the exact text
            that remains under Profile.
          </p>
        </Section>
        <Section title="What is sent to an AI provider">
          <p>
            Only after you agree, and only when live AI mode is on: the redacted resume text, your
            copilot messages, the facts in your copilot memory, and short details of the postings
            being discussed. The provider is an outside company, and identical requests may be
            answered from its shared cache.
          </p>
          <p>
            Search, matching and recommendations run on our own server and send nothing outside.
          </p>
        </Section>
        <Section title="Who can see your data">
          <p>
            Other students cannot. Coordinators see totals only. If one needs to open your record,
            they must give a reason and the view is logged. Coordinators cannot open your resume,
            your notes or your conversations. If you rate a copilot answer, coordinators can see
            that question and your comment, so that answers can be improved.
          </p>
        </Section>
        <Section title="Your choices">
          <p>
            <Link to="/account?tab=privacy" className="text-primary underline underline-offset-4">
              Under Privacy and data
            </Link>{' '}
            you can turn AI features off, download your data, or delete your account with everything
            in it.
          </p>
        </Section>
      </Card>
    </>
  );
}

export function HelpPage() {
  useTitle('Help');
  return (
    <>
      <PageHeader title="Help" />
      <Card className="p-5 sm:p-8">
        <Section title="Finding postings">
          <p>
            Search in your own words. “Teach computers to see” finds computer vision roles even if
            the posting uses other words. Filters narrow the list, and “Rank for me” orders it by
            your profile.
          </p>
        </Section>
        <Section title="What the match score means">
          <p>
            It compares the posting with your skills, preferences and profile using a fixed formula.
            Open a posting to see each part. It does not predict whether you will be selected.
          </p>
        </Section>
        <Section title="Using the copilot">
          <p>
            Ask about postings, deadlines, skill gaps or comparisons. Every posting it mentions is
            linked. It answers only from real postings, says so when it does not know, and asks
            before it saves or changes anything. There is a daily message limit, shown above the
            message box.
          </p>
        </Section>
        <Section title="Tracking applications">
          <p>
            Choose “I am interested” or “I have applied” on a posting. Move cards on the board, or
            use the stage list on each card. Every change can be undone from the message at the
            bottom of the screen. Tracking does not submit an application.
          </p>
        </Section>
        <Section title="Keyboard">
          <p>
            <kbd>Ctrl</kbd> or <kbd>⌘</kbd> + <kbd>K</kbd> opens the command palette. <kbd>/</kbd>{' '}
            moves to the search box. <kbd>Esc</kbd> closes dialogs.
          </p>
        </Section>
        <Section title="Feedback">
          <p>
            Use the feedback button at the bottom of any page, or{' '}
            <Link to="/survey" className="text-primary underline underline-offset-4">
              take the two-minute usability survey
            </Link>
            .
          </p>
        </Section>
      </Card>
    </>
  );
}
