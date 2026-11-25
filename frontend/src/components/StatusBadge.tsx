import { Archive, CheckCircle2, CircleDashed, Clock, Loader2, TriangleAlert } from 'lucide-react';
import { Badge, type Tone } from './ui/display';
import type { JobStatus } from '@/lib/types';

const styles: Record<JobStatus, { label: string; tone: Tone; icon: typeof Clock }> = {
  draft: { label: 'Draft', tone: 'neutral', icon: CircleDashed },
  pending: { label: 'Processing', tone: 'info', icon: Loader2 },
  indexed: { label: 'Live', tone: 'success', icon: CheckCircle2 },
  failed: { label: 'Failed', tone: 'danger', icon: TriangleAlert },
  expired: { label: 'Expired', tone: 'warning', icon: Clock },
  archived: { label: 'Archived', tone: 'outline', icon: Archive },
};

export function statusLabel(status: JobStatus): string {
  return styles[status].label;
}

export function StatusBadge({ status, review }: { status: JobStatus; review?: boolean }) {
  const { label, tone, icon: Icon } = styles[status];
  return (
    <Badge tone={review ? 'warning' : tone}>
      <Icon className={status === 'pending' ? 'animate-spin' : undefined} aria-hidden />
      {review ? 'Needs review' : label}
    </Badge>
  );
}
