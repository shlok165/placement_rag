import { Link } from 'react-router';
import { Alert } from '@/components/ui/display';
import { statusLabel } from '@/components/StatusBadge';
import { formatDate } from '@/lib/format';
import type { Duplicate } from '@/lib/types';

export function DuplicateWarning({ duplicates }: { duplicates: Duplicate[] }) {
  if (!duplicates.length) return null;
  return (
    <Alert tone="warning" title="This looks like a posting you already have" className="mb-4">
      <ul className="mt-1 list-disc pl-5">
        {duplicates.map((d) => (
          <li key={d.id}>
            <Link className="underline" to={`/admin/postings/${d.id}`}>
              {d.title} at {d.company}
            </Link>{' '}
            ({statusLabel(d.status)}, apply by {formatDate(d.deadline)})
          </li>
        ))}
      </ul>
      <p className="mt-1">You can still publish if this one is different.</p>
    </Alert>
  );
}
