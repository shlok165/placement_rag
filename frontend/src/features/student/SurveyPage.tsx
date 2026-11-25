import { useMutation } from '@tanstack/react-query';
import { CheckCircle2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { Button } from '@/components/ui/button';
import { Alert, Card, EmptyState, PageHeader } from '@/components/ui/display';
import { Field, Textarea } from '@/components/ui/form';
import { api, messageOf } from '@/lib/api';
import { useTitle } from '@/lib/title';

const statements = [
  'I think that I would like to use this portal frequently.',
  'I found the portal unnecessarily complex.',
  'I thought the portal was easy to use.',
  'I think that I would need the support of a technical person to use this portal.',
  'I found the various functions in this portal were well integrated.',
  'I thought there was too much inconsistency in this portal.',
  'I would imagine that most people would learn to use this portal very quickly.',
  'I found the portal very cumbersome to use.',
  'I felt very confident using the portal.',
  'I needed to learn a lot of things before I could get going with this portal.',
];

const scale = ['Strongly disagree', 'Disagree', 'Neutral', 'Agree', 'Strongly agree'];

export function SurveyPage() {
  useTitle('Usability survey');
  const [answers, setAnswers] = useState<(number | null)[]>(statements.map(() => null));
  const [comment, setComment] = useState('');
  const [missing, setMissing] = useState<number | null>(null);
  const send = useMutation({
    mutationFn: () =>
      api<{ score: number }>('/sus', { method: 'POST', body: { answers, comment } }),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const first = answers.indexOf(null);
    setMissing(first === -1 ? null : first);
    if (first === -1) send.mutate();
    else document.getElementById(`sus-${first}-1`)?.focus();
  };

  if (send.data) {
    return (
      <>
        <h1 className="sr-only">Usability survey</h1>
        <EmptyState
          icon={CheckCircle2}
          title="Thank you for your answers"
          action={
            <Button asChild>
              <Link to="/">Back to home</Link>
            </Button>
          }
        >
          Your score for the portal is {send.data.score} out of 100. Coordinators see the average
          only. Answering again replaces this response.
        </EmptyState>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Usability survey"
        description="Ten short statements from the System Usability Scale. It takes about two minutes."
      />
      <form onSubmit={submit} className="flex flex-col gap-4">
        {statements.map((statement, index) => (
          <Card key={statement} className="p-4 sm:p-5">
            <fieldset>
              <legend className="font-medium">
                {index + 1}. {statement}
              </legend>
              <div className="mt-3 grid gap-1 sm:grid-cols-5">
                {scale.map((label, value) => (
                  <label
                    key={label}
                    className="hover:bg-muted has-checked:bg-accent has-checked:text-accent-foreground flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-3 text-sm sm:flex-col sm:justify-center sm:py-3 sm:text-center"
                  >
                    <input
                      id={`sus-${index}-${value + 1}`}
                      type="radio"
                      name={`sus-${index}`}
                      className="accent-primary size-5"
                      checked={answers[index] === value + 1}
                      onChange={() =>
                        setAnswers(answers.map((a, i) => (i === index ? value + 1 : a)))
                      }
                    />
                    {label}
                  </label>
                ))}
              </div>
              {missing === index && (
                <p role="alert" className="text-danger mt-2 text-sm">
                  Choose one option.
                </p>
              )}
            </fieldset>
          </Card>
        ))}
        <Card className="p-4 sm:p-5">
          <Field label="Anything else?" hint="Optional.">
            {(ids) => (
              <Textarea
                {...ids}
                maxLength={1000}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
            )}
          </Field>
        </Card>
        {send.isError && <Alert tone="danger">{messageOf(send.error)}</Alert>}
        <Button type="submit" className="self-start" loading={send.isPending}>
          Send answers
        </Button>
      </form>
    </>
  );
}
