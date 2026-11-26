import {
  DndContext,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { useQuery } from '@tanstack/react-query';
import { ClipboardList, GripVertical, LayoutGrid, List, Pencil, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { useTrack } from './hooks';
import { QueryState } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { CalendarCard } from './CalendarCard';
import { Card, EmptyState, PageHeader } from '@/components/ui/display';
import { Field, Select, Textarea } from '@/components/ui/form';
import { Dialog } from '@/components/ui/overlay';
import { api } from '@/lib/api';
import { deadlineText, formatDate, plural } from '@/lib/format';
import { stageLabel, stageOptions, stages, type Stage } from '@/lib/stages';
import { useTitle } from '@/lib/title';
import type { Application } from '@/lib/types';
import { cn } from '@/lib/utils';

type Actions = {
  move: (row: Application, status: Stage) => void;
  edit: (row: Application) => void;
  remove: (row: Application) => void;
};

function StagePicker({ row, actions }: { row: Application; actions: Actions }) {
  return (
    <Select
      aria-label={`Stage for ${row.job.title}`}
      value={row.status}
      onValueChange={(value) => actions.move(row, value as Stage)}
      options={stageOptions}
    />
  );
}

function RowButtons({ row, actions }: { row: Application; actions: Actions }) {
  return (
    <span className="flex">
      <Button
        variant="ghost"
        size="icon"
        aria-label={`Notes for ${row.job.title}`}
        onClick={() => actions.edit(row)}
      >
        <Pencil aria-hidden />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        aria-label={`Stop tracking ${row.job.title}`}
        onClick={() => actions.remove(row)}
      >
        <Trash2 aria-hidden />
      </Button>
    </span>
  );
}

function BoardCard({ row, actions }: { row: Application; actions: Actions }) {
  const { setNodeRef, listeners, transform, isDragging } = useDraggable({ id: row.job.id });
  return (
    <div
      ref={setNodeRef}
      className={cn('bg-card rounded-md border p-3 shadow-sm', isDragging && 'z-20 shadow-lg')}
      style={
        transform
          ? { transform: `translate(${transform.x}px, ${transform.y}px)`, position: 'relative' }
          : undefined
      }
    >
      <div className="flex items-start gap-1">
        <div className="min-w-0 flex-1">
          <Link
            to={`/jobs/${row.job.id}`}
            className="text-sm font-medium underline-offset-4 hover:underline"
          >
            {row.job.title}
          </Link>
          <p className="text-muted-foreground text-xs">{row.job.company}</p>
        </div>
        {/* Pointer only. Keyboard and screen reader users change the stage with the list below. */}
        <span
          {...listeners}
          aria-hidden
          className="text-muted-foreground flex size-8 cursor-grab touch-none items-center justify-center"
        >
          <GripVertical className="size-4" />
        </span>
      </div>
      {row.notes && <p className="text-muted-foreground mt-2 line-clamp-2 text-xs">{row.notes}</p>}
      <div className="mt-2">
        <StagePicker row={row} actions={actions} />
      </div>
      <div className="mt-1 flex justify-end">
        <RowButtons row={row} actions={actions} />
      </div>
    </div>
  );
}

function Column({ stage, rows, actions }: { stage: Stage; rows: Application[]; actions: Actions }) {
  const { setNodeRef, isOver } = useDroppable({ id: stage });
  return (
    <section
      ref={setNodeRef}
      aria-label={stageLabel[stage]}
      className={cn(
        'bg-muted flex w-64 shrink-0 flex-col gap-3 rounded-lg border p-3',
        isOver && 'outline-ring outline-2',
      )}
    >
      <h2 className="flex justify-between text-sm font-semibold">
        {stageLabel[stage]}
        <span className="text-muted-foreground tabular">{rows.length}</span>
      </h2>
      {rows.map((row) => (
        <BoardCard key={row.id} row={row} actions={actions} />
      ))}
      {rows.length === 0 && <p className="text-muted-foreground py-4 text-xs">Nothing here yet</p>}
    </section>
  );
}

function Board({ rows, actions }: { rows: Application[]; actions: Actions }) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));
  const onDragEnd = ({ active, over }: DragEndEvent) => {
    const row = rows.find((r) => r.job.id === active.id);
    if (row && over && over.id !== row.status) actions.move(row, over.id as Stage);
  };
  return (
    <DndContext sensors={sensors} onDragEnd={onDragEnd}>
      <div
        role="region"
        aria-label="Application board"
        tabIndex={0}
        className="-mx-4 flex gap-3 overflow-x-auto px-4 pb-4 sm:-mx-6 sm:px-6"
      >
        {stages.map((stage) => (
          <Column
            key={stage}
            stage={stage}
            rows={rows.filter((r) => r.status === stage)}
            actions={actions}
          />
        ))}
      </div>
    </DndContext>
  );
}

function Table({ rows, actions }: { rows: Application[]; actions: Actions }) {
  return (
    <ul className="flex flex-col gap-3">
      {rows.map((row) => (
        <li key={row.id}>
          <Card className="grid items-center gap-3 p-4 sm:grid-cols-[1fr_13rem_auto]">
            <div className="min-w-0">
              <Link
                to={`/jobs/${row.job.id}`}
                className="font-medium underline-offset-4 hover:underline"
              >
                {row.job.title}
              </Link>
              <p className="text-muted-foreground text-sm">
                {row.job.company} · {deadlineText(row.job.deadline)} · Changed{' '}
                {formatDate(row.updated_at)}
              </p>
              {row.notes && <p className="mt-1 text-sm break-words">{row.notes}</p>}
            </div>
            <StagePicker row={row} actions={actions} />
            <RowButtons row={row} actions={actions} />
          </Card>
        </li>
      ))}
    </ul>
  );
}

export function ApplicationsPage() {
  useTitle('Applications');
  const track = useTrack();
  const query = useQuery({
    queryKey: ['applications'],
    queryFn: () => api<Application[]>('/applications'),
  });
  const [view, setView] = useState<'board' | 'list'>('board');
  const [editing, setEditing] = useState<Application | null>(null);
  const [notes, setNotes] = useState('');

  const actions: Actions = {
    move: (row, status) => track({ jobId: row.job.id, status, previous: row.status }),
    remove: (row) =>
      track({
        jobId: row.job.id,
        status: null,
        previous: row.status,
        previousNotes: row.notes,
      }),
    edit: (row) => {
      setNotes(row.notes);
      setEditing(row);
    },
  };

  return (
    <>
      <PageHeader
        title="Applications"
        description={
          query.data?.length ? `${plural(query.data.length, 'application')} tracked` : undefined
        }
        actions={
          <div role="group" aria-label="View" className="flex gap-1">
            <Button
              variant={view === 'board' ? 'primary' : 'secondary'}
              aria-pressed={view === 'board'}
              onClick={() => setView('board')}
            >
              <LayoutGrid aria-hidden />
              Board
            </Button>
            <Button
              variant={view === 'list' ? 'primary' : 'secondary'}
              aria-pressed={view === 'list'}
              onClick={() => setView('list')}
            >
              <List aria-hidden />
              List
            </Button>
          </div>
        }
      />
      <QueryState query={query}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState
              icon={ClipboardList}
              title="You are not tracking anything yet"
              action={
                <Button asChild>
                  <Link to="/jobs">Find a posting</Link>
                </Button>
              }
            >
              Open a posting and choose “I am interested” or “I have applied”. Stages and notes stay
              private to you.
            </EmptyState>
          ) : view === 'board' ? (
            <Board rows={rows} actions={actions} />
          ) : (
            <Table rows={rows} actions={actions} />
          )
        }
      </QueryState>
      <div className="mt-8 max-w-2xl">
        <CalendarCard />
      </div>
      <Dialog
        open={editing !== null}
        onOpenChange={(open) => !open && setEditing(null)}
        title={editing ? `Notes for ${editing.job.title}` : 'Notes'}
      >
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (editing) track({ jobId: editing.job.id, status: editing.status, notes });
            setEditing(null);
          }}
        >
          <Field label="Notes" hint="Only you can see these.">
            {(ids) => (
              <Textarea
                {...ids}
                rows={5}
                maxLength={2000}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            )}
          </Field>
          <Button type="submit" className="self-end">
            Save notes
          </Button>
        </form>
      </Dialog>
    </>
  );
}
