import { useQuery } from '@tanstack/react-query';
import { Bell, Megaphone, X } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { AppShell } from '@/app/AppShell';
import { Button } from '@/components/ui/button';
import { Tooltip } from '@/components/ui/overlay';
import { api } from '@/lib/api';

function UnreadBell() {
  const { data } = useQuery({
    queryKey: ['unread'],
    queryFn: () => api<{ unread: number }>('/notifications/unread'),
    refetchInterval: 60_000,
  });
  const unread = data?.unread ?? 0;
  return (
    <Tooltip content="Notifications">
      <Button asChild variant="ghost" size="icon" className="relative">
        <Link
          to="/notifications"
          aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
        >
          <Bell aria-hidden />
          {unread > 0 && (
            <span
              aria-hidden
              className="bg-primary text-primary-foreground tabular absolute top-1 right-1 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[0.625rem] font-semibold"
            >
              {unread > 9 ? '9+' : unread}
            </span>
          )}
        </Link>
      </Button>
    </Tooltip>
  );
}

function Banner() {
  const { data } = useQuery({
    queryKey: ['announcement'],
    queryFn: () => api<{ id: number | null; message: string | null }>('/announcement'),
    staleTime: 5 * 60_000,
  });
  const [hidden, setHidden] = useState<number | null>(null);
  if (!data?.message || data.id === hidden) return null;
  return (
    <div
      role="status"
      className="bg-accent text-accent-foreground flex items-center gap-3 px-4 py-2 text-sm sm:px-6"
    >
      <Megaphone className="size-4 shrink-0" aria-hidden />
      <p className="flex-1">{data.message}</p>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Hide announcement"
        onClick={() => setHidden(data.id)}
      >
        <X aria-hidden />
      </Button>
    </div>
  );
}

export function StudentShell() {
  return <AppShell portal="student" topbar={<UnreadBell />} banner={<Banner />} />;
}
