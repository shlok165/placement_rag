import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookmarkPlus, History, Search, SearchX, SlidersHorizontal, X } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router';
import { toast } from 'sonner';
import { JobCard } from './JobCard';
import { addRecent, clearRecent, readRecent } from './recent';
import { Pagination } from '@/components/Pagination';
import { QueryState } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { Alert, EmptyState, PageHeader } from '@/components/ui/display';
import { CheckRow, Field, Input, Select, Switch } from '@/components/ui/form';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { api, messageOf } from '@/lib/api';
import { plural } from '@/lib/format';
import { useTitle } from '@/lib/title';
import type { ParsedQuery, SavedSearch, SearchFilters, SearchResult } from '@/lib/types';
import { locationOptions } from '@/lib/vocabulary';

const PAGE_SIZE = 12;
const FILTER_KEYS = ['type', 'loc', 'remote', 'pay', 'days'] as const;

function readFilters(params: URLSearchParams): SearchFilters {
  return {
    job_type: (params.get('type') as SearchFilters['job_type']) || null,
    locations: params.getAll('loc'),
    remote: params.get('remote') === '1' ? true : params.get('remote') === '0' ? false : null,
    min_stipend: Number(params.get('pay')) || null,
    closing_within_days: Number(params.get('days')) || null,
  };
}

function writeFilters(params: URLSearchParams, filters: SearchFilters) {
  FILTER_KEYS.forEach((key) => params.delete(key));
  if (filters.job_type) params.set('type', filters.job_type);
  filters.locations?.forEach((loc) => params.append('loc', loc));
  if (filters.remote === true) params.set('remote', '1');
  if (filters.remote === false) params.set('remote', '0');
  if (filters.min_stipend) params.set('pay', String(filters.min_stipend));
  if (filters.closing_within_days) params.set('days', String(filters.closing_within_days));
}

function FilterPanel({
  filters,
  onChange,
}: {
  filters: SearchFilters;
  onChange: (filters: SearchFilters) => void;
}) {
  const chosen = filters.locations ?? [];
  return (
    <div className="flex flex-col gap-5">
      <Field label="Type">
        {(ids) => (
          <Select
            {...ids}
            value={filters.job_type ?? 'all'}
            onValueChange={(v) =>
              onChange({ ...filters, job_type: v === 'all' ? null : (v as 'internship') })
            }
            options={[
              { value: 'all', label: 'Any' },
              { value: 'internship', label: 'Internship' },
              { value: 'full-time', label: 'Full-time' },
            ]}
          />
        )}
      </Field>
      <Field label="Pay at least">
        {(ids) => (
          <Select
            {...ids}
            value={String(filters.min_stipend ?? 0)}
            onValueChange={(v) => onChange({ ...filters, min_stipend: Number(v) || null })}
            options={[
              { value: '0', label: 'Any amount' },
              { value: '20000', label: '₹20,000' },
              { value: '40000', label: '₹40,000' },
              { value: '60000', label: '₹60,000' },
            ]}
          />
        )}
      </Field>
      <Field label="Closing">
        {(ids) => (
          <Select
            {...ids}
            value={String(filters.closing_within_days ?? 0)}
            onValueChange={(v) => onChange({ ...filters, closing_within_days: Number(v) || null })}
            options={[
              { value: '0', label: 'Any time' },
              { value: '3', label: 'Within 3 days' },
              { value: '7', label: 'Within 7 days' },
              { value: '30', label: 'Within 30 days' },
            ]}
          />
        )}
      </Field>
      <CheckRow
        label="Remote only"
        checked={!!filters.remote}
        onCheckedChange={(on) => onChange({ ...filters, remote: on || null })}
      />
      <fieldset>
        <legend className="mb-1 text-sm font-medium">Location</legend>
        {locationOptions.slice(0, 9).map((location) => (
          <CheckRow
            key={location}
            label={location}
            checked={chosen.includes(location)}
            onCheckedChange={(on) =>
              onChange({
                ...filters,
                locations: on ? [...chosen, location] : chosen.filter((l) => l !== location),
              })
            }
          />
        ))}
      </fieldset>
    </div>
  );
}

function filterChips(filters: SearchFilters): { label: string; without: SearchFilters }[] {
  const chips: { label: string; without: SearchFilters }[] = [];
  if (filters.job_type)
    chips.push({
      label: filters.job_type === 'internship' ? 'Internship' : 'Full-time',
      without: { ...filters, job_type: null },
    });
  if (filters.remote) chips.push({ label: 'Remote', without: { ...filters, remote: null } });
  if (filters.remote === false)
    chips.push({ label: 'Not remote', without: { ...filters, remote: null } });
  if (filters.min_stipend)
    chips.push({
      label: `₹${filters.min_stipend.toLocaleString('en-IN')} or more`,
      without: { ...filters, min_stipend: null },
    });
  if (filters.closing_within_days)
    chips.push({
      label: `Closing within ${filters.closing_within_days} days`,
      without: { ...filters, closing_within_days: null },
    });
  filters.locations?.forEach((loc) =>
    chips.push({
      label: loc,
      without: { ...filters, locations: filters.locations!.filter((l) => l !== loc) },
    }),
  );
  return chips;
}

export function BrowsePage() {
  useTitle('Browse');
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const query = params.get('q') ?? '';
  const sort = params.get('sort') ?? 'relevance';
  const page = Number(params.get('page')) || 1;
  const personal = params.get('personal') !== '0';
  const filters = readFilters(params);

  const [text, setText] = useState(query);
  const [lastQuery, setLastQuery] = useState(query);
  const [recent, setRecent] = useState(readRecent);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState('');
  // Filters read from the typed words, shown for a check before they are applied.
  const [pending, setPending] = useState<ParsedQuery | null>(null);

  // Follow changes that come from outside the box: back button, saved or recent searches.
  if (query !== lastQuery) {
    setLastQuery(query);
    setText(query);
  }

  const change = (edit: (next: URLSearchParams) => void, replace = false) => {
    const next = new URLSearchParams(params);
    next.delete('page');
    edit(next);
    setParams(next, { replace });
  };
  const setFilters = (next: SearchFilters) => change((p) => writeFilters(p, next));
  const runSearch = (value: string) => {
    const clean = value.trim();
    setText(clean);
    if (clean) setRecent(addRecent(clean));
    change((p) => (clean ? p.set('q', clean) : p.delete('q')));
  };

  const body = {
    query,
    filters,
    personalize: personal,
    sort,
    page,
    page_size: PAGE_SIZE,
  };
  const results = useQuery({
    queryKey: ['search', body],
    queryFn: ({ signal }) => api<SearchResult>('/search', { method: 'POST', body, signal }),
    placeholderData: keepPreviousData,
  });
  const saved = useQuery({
    queryKey: ['saved-searches'],
    queryFn: () => api<SavedSearch[]>('/saved-searches'),
  });
  const saveSearch = useMutation({
    mutationFn: () =>
      api('/saved-searches', { method: 'POST', body: { name: name.trim(), query, filters } }),
    onSuccess: () => {
      setNaming(false);
      toast.success('Search saved');
      client.invalidateQueries({ queryKey: ['saved-searches'] });
    },
    onError: (error) => toast.error(messageOf(error)),
  });
  const removeSearch = useMutation({
    mutationFn: (id: number) => api<void>(`/saved-searches/${id}`, { method: 'DELETE' }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['saved-searches'] }),
  });

  const chips = filterChips(filters);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const clean = text.trim();
    setPending(null);
    if (clean) {
      try {
        const parsed = await api<ParsedQuery>('/search/parse', {
          method: 'POST',
          body: { text: clean },
        });
        if (parsed.chips.length) {
          setPending(parsed);
          return;
        }
      } catch {
        // Reading filters is a convenience; the words still go to search.
      }
    }
    runSearch(clean);
  };
  const applyPending = (parsed: ParsedQuery) => {
    const next: SearchFilters = { ...filters, locations: [...(filters.locations ?? [])] };
    for (const chip of parsed.chips) {
      if (chip.key === 'locations') {
        if (!next.locations!.includes(chip.value)) next.locations!.push(chip.value);
      } else {
        Object.assign(next, { [chip.key]: parsed.filters[chip.key] });
      }
    }
    const clean = parsed.query.trim();
    setPending(null);
    setText(clean);
    if (clean) setRecent(addRecent(clean));
    change((p) => {
      if (clean) p.set('q', clean);
      else p.delete('q');
      writeFilters(p, next);
    });
  };
  const dropChip = (parsed: ParsedQuery, index: number) => {
    const chip = parsed.chips[index];
    const chipsLeft = parsed.chips.filter((_, i) => i !== index);
    const words = chip.key === 'locations' ? chip.label : '';
    setPending({
      ...parsed,
      chips: chipsLeft,
      query: words ? `${parsed.query} ${words}`.trim() : parsed.query,
    });
  };

  return (
    <>
      <PageHeader title="Browse postings" />
      <form onSubmit={submit} role="search" className="flex gap-2">
        <div className="relative flex-1">
          <Search
            className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
            aria-hidden
          />
          <Input
            type="search"
            data-search-input
            aria-label="Search postings"
            placeholder="Try “remote data science” or “work with farmers”"
            className="h-12 pl-9 sm:h-11"
            maxLength={300}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <Button type="submit" className="h-12 sm:h-11">
          Search
        </Button>
      </form>

      <div aria-live="polite">
        {pending && (
          <section
            aria-labelledby="understood"
            className="bg-card mt-3 flex flex-col gap-3 rounded-lg border p-4"
          >
            <h2 id="understood" className="text-sm font-semibold">
              Use these as filters?
            </h2>
            <ul className="flex flex-wrap gap-2">
              {pending.chips.map((chip, index) => (
                <li key={`${chip.key}-${chip.value}`}>
                  <span className="bg-secondary flex min-h-9 items-center gap-1 rounded-full pr-1 pl-3 text-sm">
                    {chip.label}
                    <button
                      type="button"
                      aria-label={`Remove ${chip.label}`}
                      className="hover:bg-muted flex size-7 items-center justify-center rounded-full"
                      onClick={() => dropChip(pending, index)}
                    >
                      <X className="size-3.5" aria-hidden />
                    </button>
                  </span>
                </li>
              ))}
            </ul>
            <p className="text-muted-foreground text-sm">
              {pending.query ? (
                <>
                  Search words: <span className="text-foreground">“{pending.query}”</span>
                </>
              ) : (
                'No search words left: postings are filtered only.'
              )}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => applyPending(pending)}>
                Search with {pending.chips.length ? 'these filters' : 'these words'}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setPending(null);
                  runSearch(text);
                }}
              >
                Search my words as typed
              </Button>
            </div>
          </section>
        )}
      </div>

      {!query && recent.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          <History className="text-muted-foreground size-4" aria-hidden />
          <span className="text-muted-foreground">Recent:</span>
          {recent.map((item) => (
            <Button key={item} variant="secondary" size="sm" onClick={() => runSearch(item)}>
              {item}
            </Button>
          ))}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              clearRecent();
              setRecent([]);
            }}
          >
            Clear
          </Button>
        </div>
      )}
      {!!saved.data?.length && (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">Saved searches:</span>
          {saved.data.map((item) => (
            <span key={item.id} className="bg-card flex items-center rounded-md border">
              <button
                type="button"
                className="hover:bg-muted min-h-9 rounded-l-md px-3 font-medium"
                onClick={() => {
                  setText(item.query);
                  const next = new URLSearchParams();
                  if (item.query) next.set('q', item.query);
                  writeFilters(next, item.filters);
                  setParams(next);
                }}
              >
                {item.name}
              </button>
              <button
                type="button"
                className="hover:bg-muted flex size-9 items-center justify-center rounded-r-md"
                aria-label={`Delete saved search ${item.name}`}
                onClick={() => removeSearch.mutate(item.id)}
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[14rem_1fr]">
        <aside className="hidden lg:block" aria-label="Filters">
          <FilterPanel filters={filters} onChange={setFilters} />
        </aside>
        <section aria-label="Results" aria-busy={results.isFetching} className="min-w-0">
          <h2 className="sr-only">Results</h2>
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <p className="text-muted-foreground mr-auto text-sm" aria-live="polite">
              {results.data ? plural(results.data.total, 'posting') : 'Searching'}
            </p>
            <Button variant="secondary" className="lg:hidden" onClick={() => setFiltersOpen(true)}>
              <SlidersHorizontal aria-hidden />
              Filters{chips.length > 0 && ` (${chips.length})`}
            </Button>
            <span className="flex min-h-10 items-center gap-2 text-sm">
              <Switch
                id="personal"
                checked={personal}
                onCheckedChange={(on) =>
                  change((p) => (on ? p.delete('personal') : p.set('personal', '0')))
                }
              />
              <label htmlFor="personal">Rank for me</label>
            </span>
            <div className="w-44">
              <Select
                aria-label="Sort by"
                value={sort}
                onValueChange={(v) =>
                  change((p) => (v === 'relevance' ? p.delete('sort') : p.set('sort', v)))
                }
                options={[
                  { value: 'relevance', label: 'Best match' },
                  { value: 'deadline', label: 'Closing soon' },
                  { value: 'newest', label: 'Newest' },
                  { value: 'stipend', label: 'Highest pay' },
                ]}
              />
            </div>
          </div>
          {(chips.length > 0 || query) && (
            <div className="mb-4 flex flex-wrap items-center gap-2">
              {chips.map((chip) => (
                <button
                  key={chip.label}
                  type="button"
                  className="bg-accent text-accent-foreground flex min-h-8 items-center gap-1 rounded-full px-3 text-sm"
                  onClick={() => setFilters(chip.without)}
                >
                  {chip.label}
                  <X className="size-3.5" aria-hidden />
                  <span className="sr-only">Remove filter</span>
                </button>
              ))}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setName(query || chips.map((c) => c.label).join(', '));
                  setNaming(true);
                }}
              >
                <BookmarkPlus aria-hidden />
                Save this search
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setText('');
                  setParams({});
                }}
              >
                Clear all
              </Button>
            </div>
          )}
          <QueryState query={results}>
            {(data) =>
              data.items.length === 0 ? (
                <EmptyState
                  icon={SearchX}
                  title="No postings match"
                  action={
                    chips.length > 0 && (
                      <Button variant="secondary" onClick={() => setFilters({})}>
                        Remove all filters
                      </Button>
                    )
                  }
                >
                  Try fewer filters, a broader phrase such as a skill or a field, or save this
                  search and check back later.
                </EmptyState>
              ) : (
                <>
                  {data.weak_match && (
                    <Alert tone="info" className="mb-4" title="Nothing is a close match">
                      These are only the nearest postings. Try a skill, a role or a city.
                    </Alert>
                  )}
                  {personal && !data.personalized && (
                    <p className="text-muted-foreground mb-3 text-sm">
                      Add skills or preferences to your profile to rank results for you.
                    </p>
                  )}
                  <ul className="flex flex-col gap-4">
                    {data.items.map((hit) => (
                      <li key={hit.job.id}>
                        <JobCard hit={hit} />
                      </li>
                    ))}
                  </ul>
                  <Pagination
                    page={data.page}
                    pageSize={data.page_size}
                    total={data.total}
                    onChange={(next) => {
                      const updated = new URLSearchParams(params);
                      updated.set('page', String(next));
                      setParams(updated);
                      window.scrollTo(0, 0);
                    }}
                  />
                </>
              )
            }
          </QueryState>
        </section>
      </div>
      <Sheet open={filtersOpen} onOpenChange={setFiltersOpen} title="Filters" side="right">
        <FilterPanel filters={filters} onChange={setFilters} />
        <Button className="mt-6" onClick={() => setFiltersOpen(false)}>
          Show results
        </Button>
      </Sheet>
      <Dialog open={naming} onOpenChange={setNaming} title="Save this search">
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            saveSearch.mutate();
          }}
        >
          <Field label="Name">
            {(ids) => (
              <Input
                {...ids}
                required
                maxLength={80}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            )}
          </Field>
          <Button type="submit" className="self-end" loading={saveSearch.isPending}>
            Save
          </Button>
        </form>
      </Dialog>
    </>
  );
}
