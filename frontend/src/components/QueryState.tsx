import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { Button } from './ui/button';
import { Alert, LoadingRows } from './ui/display';
import { messageOf } from '@/lib/api';

/** Skeleton while loading, a plain message with retry on error, content otherwise. */
export function QueryState<T>({
  query,
  children,
  loading,
}: {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
  loading?: ReactNode;
}) {
  if (query.isPending) return loading ?? <LoadingRows />;
  if (query.isError && query.data === undefined) {
    return (
      <Alert
        tone="danger"
        title="This could not be loaded"
        action={
          <Button variant="secondary" size="sm" onClick={() => query.refetch()}>
            Try again
          </Button>
        }
      >
        {messageOf(query.error)}
      </Alert>
    );
  }
  return <>{children(query.data as T)}</>;
}
