import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, messageOf } from '@/lib/api';
import { stageLabel, type Stage } from '@/lib/stages';
import type { Application, Home, JobDetail, SearchHit, SearchResult } from '@/lib/types';

type Snapshot = [QueryKey, unknown][];

const LISTS: QueryKey[] = [['search'], ['home'], ['saved'], ['job']];

/** Apply one change to a posting wherever it is cached: lists, home and detail. */
function patchHit(data: unknown, jobId: number, change: Partial<SearchHit>): unknown {
  const patch = (hit: SearchHit) => (hit.job.id === jobId ? { ...hit, ...change } : hit);
  if (Array.isArray(data)) return (data as SearchHit[]).map(patch);
  if (!data || typeof data !== 'object') return data;
  if ('items' in data) {
    const page = data as SearchResult;
    return { ...page, items: page.items.map(patch) };
  }
  if ('recommended' in data) {
    const home = data as Home;
    return {
      ...home,
      recommended: home.recommended.map(patch),
      closing_soon: home.closing_soon.map(patch),
    };
  }
  const detail = data as JobDetail;
  if (detail.job?.id === jobId && 'saved' in change) return { ...detail, saved: change.saved };
  return data;
}

function useOptimisticHit() {
  const client = useQueryClient();
  return {
    client,
    apply: async (jobId: number, change: Partial<SearchHit>): Promise<Snapshot> => {
      const snapshot: Snapshot = [];
      for (const queryKey of LISTS) {
        await client.cancelQueries({ queryKey });
        snapshot.push(...client.getQueriesData({ queryKey }));
        client.setQueriesData({ queryKey }, (data: unknown) => patchHit(data, jobId, change));
      }
      return snapshot;
    },
    rollback: (snapshot?: Snapshot) =>
      snapshot?.forEach(([key, data]) => client.setQueryData(key, data)),
  };
}

export function useSaveJob() {
  const { client, apply, rollback } = useOptimisticHit();
  const mutation = useMutation({
    mutationFn: ({ jobId, saved }: { jobId: number; saved: boolean }) =>
      api<void>(`/saved/${jobId}`, { method: saved ? 'PUT' : 'DELETE' }),
    onMutate: ({ jobId, saved }) => apply(jobId, { saved }),
    onError: (error, _, snapshot) => {
      rollback(snapshot);
      toast.error(messageOf(error));
    },
    onSettled: () => client.invalidateQueries({ queryKey: ['saved'] }),
  });
  return (jobId: number, saved: boolean, quiet = false) =>
    mutation.mutate(
      { jobId, saved },
      {
        onSuccess: () => {
          if (quiet) return;
          toast.success(saved ? 'Saved' : 'Removed from saved', {
            action: { label: 'Undo', onClick: () => mutation.mutate({ jobId, saved: !saved }) },
          });
        },
      },
    );
}

type TrackInput = {
  jobId: number;
  /** null stops tracking. */
  status: Stage | null;
  notes?: string;
  /** Set to offer an undo; null means it was not tracked before. */
  previous?: Stage | null;
  previousNotes?: string;
};

export function useTrack() {
  const { client, apply, rollback } = useOptimisticHit();
  const mutation = useMutation({
    mutationFn: ({ jobId, status, notes }: TrackInput): Promise<Application | void> =>
      status === null
        ? api<void>(`/applications/${jobId}`, { method: 'DELETE' })
        : api<Application>(`/applications/${jobId}`, { method: 'PUT', body: { status, notes } }),
    onMutate: async ({ jobId, status }): Promise<Snapshot> => {
      const snapshot = await apply(jobId, { application_status: status });
      await client.cancelQueries({ queryKey: ['applications'] });
      const previous = client.getQueryData<Application[]>(['applications']);
      snapshot.push([['applications'], previous]);
      client.setQueryData<Application[]>(['applications'], (rows) =>
        status === null
          ? rows?.filter((r) => r.job.id !== jobId)
          : rows?.map((r) => (r.job.id === jobId ? { ...r, status } : r)),
      );
      return snapshot;
    },
    onError: (error, _, snapshot) => {
      rollback(snapshot);
      toast.error(messageOf(error));
    },
    onSettled: (_data, _error, { jobId }) => {
      client.invalidateQueries({ queryKey: ['applications'] });
      client.invalidateQueries({ queryKey: ['job', jobId] });
      client.invalidateQueries({ queryKey: ['home'] });
    },
  });
  return (input: TrackInput) =>
    mutation.mutate(input, {
      onSuccess: () => {
        if (input.previous === undefined) return;
        const text =
          input.status === null ? 'Stopped tracking' : `Moved to ${stageLabel[input.status]}`;
        toast.success(text, {
          action: {
            label: 'Undo',
            onClick: () =>
              mutation.mutate({
                jobId: input.jobId,
                status: input.previous ?? null,
                notes: input.previousNotes,
              }),
          },
        });
      },
    });
}
