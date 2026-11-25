import { useMutation, useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { StatTile } from '@/components/BarList';
import { QueryState } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { Alert, Badge, Card, PageHeader } from '@/components/ui/display';
import { Field, Input } from '@/components/ui/form';
import { api, messageOf } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { stageLabel, type Stage } from '@/lib/stages';
import { useTitle } from '@/lib/title';

type Overview = {
  total: number;
  active: number;
  onboarded: number;
  with_resume: number;
  tracking: number;
};
type Student = {
  full_name: string;
  email: string;
  joined: string;
  last_seen: string | null;
  onboarded: boolean;
  skills: string[];
  applications: {
    status: Stage;
    updated_at: string;
    job_id: number;
    title: string;
    company: string;
  }[];
};

export function StudentsPage() {
  useTitle('Students');
  const overview = useQuery({
    queryKey: ['students'],
    queryFn: () => api<Overview>('/admin/students'),
  });
  const [form, setForm] = useState({ email: '', reason: '' });
  const lookup = useMutation({
    mutationFn: () => api<Student>('/admin/students/lookup', { method: 'POST', body: form }),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    lookup.mutate();
  };

  return (
    <>
      <PageHeader
        title="Students"
        description="Totals only. Opening one student's record needs a reason and is written to the audit log."
      />
      <QueryState query={overview}>
        {(o) => (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <StatTile label="Registered" value={o.total} />
            <StatTile label="Active" value={o.active} hint="Last 14 days" />
            <StatTile label="Onboarded" value={o.onboarded} />
            <StatTile label="With a resume" value={o.with_resume} />
            <StatTile label="Tracking applications" value={o.tracking} />
          </div>
        )}
      </QueryState>
      <Card className="mt-6 p-5">
        <h2 className="font-semibold">Look up one student</h2>
        <form onSubmit={submit} className="mt-4 grid items-end gap-4 sm:grid-cols-[1fr_1fr_auto]">
          <Field label="Student email">
            {(ids) => (
              <Input
                {...ids}
                type="email"
                required
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            )}
          </Field>
          <Field label="Reason">
            {(ids) => (
              <Input
                {...ids}
                required
                minLength={5}
                maxLength={200}
                placeholder="For example, confirming an offer"
                value={form.reason}
                onChange={(e) => setForm({ ...form, reason: e.target.value })}
              />
            )}
          </Field>
          <Button type="submit" variant="secondary" loading={lookup.isPending}>
            <Search aria-hidden />
            Look up
          </Button>
        </form>
        {lookup.isError && (
          <Alert tone="danger" className="mt-4">
            {messageOf(lookup.error)}
          </Alert>
        )}
        {lookup.data && (
          <div className="mt-6 border-t pt-5" role="status">
            <h3 className="font-semibold">{lookup.data.full_name}</h3>
            <p className="text-muted-foreground text-sm">
              Joined {formatDate(lookup.data.joined)}, last seen {formatDate(lookup.data.last_seen)}
            </p>
            <p className="mt-3 flex flex-wrap gap-2">
              {lookup.data.skills.map((s) => (
                <Badge key={s}>{s}</Badge>
              ))}
            </p>
            <h4 className="mt-4 text-sm font-medium">Applications</h4>
            {lookup.data.applications.length ? (
              <ul className="divide-y text-sm">
                {lookup.data.applications.map((a) => (
                  <li key={a.job_id} className="flex justify-between gap-3 py-2">
                    <span>
                      {a.title} <span className="text-muted-foreground">· {a.company}</span>
                    </span>
                    <Badge tone="accent">{stageLabel[a.status]}</Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground text-sm">None tracked.</p>
            )}
          </div>
        )}
      </Card>
    </>
  );
}
