import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/overlay';

const steps = [
  {
    title: 'Find postings in your own words',
    text: 'Browse understands meaning as well as exact words. Filters sit beside the results, and “Rank for me” orders them by your profile.',
  },
  {
    title: 'See why something fits',
    text: 'Every posting shows which skills match and which are missing. The score compares fit only and does not predict selection.',
  },
  {
    title: 'Ask the copilot',
    text: 'It answers only from real postings, links each one, and asks before it saves or changes anything.',
  },
  {
    title: 'Keep track',
    text: 'Save postings, move applications through stages and get reminders before deadlines. Changes can be undone.',
  },
  {
    title: 'Move faster',
    text: 'Press Ctrl or ⌘ + K for the command palette, or / to jump to search. You can reopen this tour from Help.',
  },
];

const SEEN_KEY = 'tour-seen';
export const OPEN_TOUR = 'open-tour';

function seen(): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) === '1';
  } catch {
    return true;
  }
}

/** First-run tour. It can be skipped at any step and reopened from Help. */
export function Tour() {
  const [open, setOpen] = useState(() => !seen());
  const [step, setStep] = useState(0);

  useEffect(() => {
    const show = () => {
      setStep(0);
      setOpen(true);
    };
    window.addEventListener(OPEN_TOUR, show);
    return () => window.removeEventListener(OPEN_TOUR, show);
  }, []);

  const close = () => {
    setOpen(false);
    try {
      localStorage.setItem(SEEN_KEY, '1');
    } catch {
      // Without storage the tour shows again on the next visit.
    }
  };
  const last = step === steps.length - 1;

  return (
    <Dialog
      open={open}
      onOpenChange={(value) => (value ? setOpen(true) : close())}
      title={steps[step].title}
      description={steps[step].text}
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-muted-foreground text-sm" aria-live="polite">
          {step + 1} of {steps.length}
        </p>
        <div className="flex gap-2">
          {!last && (
            <Button variant="ghost" onClick={close}>
              Skip tour
            </Button>
          )}
          {step > 0 && (
            <Button variant="secondary" onClick={() => setStep(step - 1)}>
              Back
            </Button>
          )}
          <Button onClick={() => (last ? close() : setStep(step + 1))}>
            {last ? 'Done' : 'Next'}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
