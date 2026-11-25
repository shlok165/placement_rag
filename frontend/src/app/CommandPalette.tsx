import { useQuery } from '@tanstack/react-query';
import { Command } from 'cmdk';
import { Briefcase, Search } from 'lucide-react';
import { Dialog as DialogPrimitive } from 'radix-ui';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { adminNav, adminSecondaryNav, studentNav, studentSecondaryNav } from './nav';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import type { AdminJobRow, Page, SearchResult } from '@/lib/types';

const itemClass =
  'data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground flex min-h-11 cursor-pointer items-center gap-3 rounded-md px-3 text-sm [&_svg]:size-4';

type Found = { id: number; title: string; company: string };

function typingInField(target: EventTarget | null) {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))
  );
}

/** `/` focuses the search box on the page, or opens the palette when there is none. */
function focusSearch(): boolean {
  const box = document.querySelector<HTMLInputElement>('[data-search-input]');
  box?.focus();
  return box !== null;
}

export function CommandPalette({ portal }: { portal: 'student' | 'admin' }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const navigate = useNavigate();
  const pages =
    portal === 'admin'
      ? [...adminNav, ...adminSecondaryNav]
      : [...studentNav, ...studentSecondaryNav];
  const query = text.trim();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setOpen((value) => !value);
      } else if (event.key === '/' && !typingInField(event.target)) {
        event.preventDefault();
        if (!focusSearch()) setOpen(true);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const found = useQuery({
    queryKey: ['palette', portal, query],
    enabled: open && query.length > 1,
    staleTime: 10_000,
    queryFn: async ({ signal }): Promise<Found[]> => {
      if (portal === 'admin') {
        const params = new URLSearchParams({ q: query, page_size: '5' });
        return (await api<Page<AdminJobRow>>(`/admin/jobs?${params}`, { signal })).items;
      }
      const body = { query, personalize: true, page_size: 5 };
      const result = await api<SearchResult>('/search', { method: 'POST', body, signal });
      return result.items.map((hit) => hit.job);
    },
  });

  const go = (to: string) => {
    setOpen(false);
    setText('');
    navigate(to);
  };
  const matches = pages.filter((p) => p.label.toLowerCase().includes(query.toLowerCase()));

  return (
    <>
      <Button
        variant="secondary"
        className="text-muted-foreground px-3 sm:w-56 sm:justify-start"
        aria-label="Search and commands"
        onClick={() => setOpen(true)}
      >
        <Search aria-hidden />
        <span className="hidden flex-1 text-left font-normal sm:inline">Search or jump to</span>
        <kbd className="hidden rounded border px-1.5 text-xs sm:inline" aria-hidden>
          Ctrl K
        </kbd>
      </Button>
      <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay className="animate-overlay fixed inset-0 z-40 bg-black/50" />
          <DialogPrimitive.Content
            aria-describedby={undefined}
            className="animate-panel bg-popover fixed top-[12vh] left-1/2 z-50 w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-lg border shadow-lg"
          >
            <DialogPrimitive.Title className="sr-only">Search and commands</DialogPrimitive.Title>
            <Command shouldFilter={false} label="Search and commands">
              <Command.Input
                value={text}
                onValueChange={setText}
                placeholder="Type a page or a posting"
                className="placeholder:text-muted-foreground h-14 w-full border-b bg-transparent px-4 text-base -outline-offset-2"
              />
              <Command.List className="max-h-[50vh] overflow-y-auto p-2">
                <Command.Empty className="text-muted-foreground p-6 text-center text-sm">
                  {found.isFetching ? 'Searching' : 'Nothing found. Try a shorter word.'}
                </Command.Empty>
                {matches.length > 0 && (
                  <Command.Group
                    heading="Pages"
                    className="[&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs"
                  >
                    {matches.map(({ to, label, icon: Icon }) => (
                      <Command.Item
                        key={to}
                        value={`page ${to}`}
                        onSelect={() => go(to)}
                        className={itemClass}
                      >
                        <Icon aria-hidden />
                        {label}
                      </Command.Item>
                    ))}
                  </Command.Group>
                )}
                {!!found.data?.length && (
                  <Command.Group
                    heading="Postings"
                    className="[&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs"
                  >
                    {found.data.map((job) => (
                      <Command.Item
                        key={job.id}
                        value={`job ${job.id}`}
                        onSelect={() =>
                          go(portal === 'admin' ? `/admin/postings/${job.id}` : `/jobs/${job.id}`)
                        }
                        className={itemClass}
                      >
                        <Briefcase aria-hidden />
                        <span className="truncate">
                          {job.title} <span className="text-muted-foreground">· {job.company}</span>
                        </span>
                      </Command.Item>
                    ))}
                  </Command.Group>
                )}
                {query.length > 1 && (
                  <Command.Item
                    value="search all"
                    onSelect={() =>
                      go(
                        `${portal === 'admin' ? '/admin/postings' : '/jobs'}?q=${encodeURIComponent(query)}`,
                      )
                    }
                    className={itemClass}
                  >
                    <Search aria-hidden />
                    See all results for “{query}”
                  </Command.Item>
                )}
              </Command.List>
            </Command>
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>
    </>
  );
}
