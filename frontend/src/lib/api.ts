export type FieldError = { field: string; message: string };

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
    public requestId?: string,
  ) {
    super(message);
  }

  fieldError(field: string): string | undefined {
    if (!Array.isArray(this.details)) return undefined;
    return (this.details as FieldError[]).find((d) => d.field === field)?.message;
  }
}

function csrfToken(): string {
  return document.cookie.match(/(?:^|; )csrf_token=([^;]+)/)?.[1] ?? '';
}

export function csrfHeaders(): Record<string, string> {
  return { 'X-CSRF-Token': csrfToken() };
}

export async function toApiError(response: Response): Promise<ApiError> {
  try {
    const { error } = await response.json();
    return new ApiError(
      response.status,
      error.code,
      error.message,
      error.details,
      error.request_id,
    );
  } catch {
    return new ApiError(
      response.status,
      'unavailable',
      'The server is not reachable right now. Check your connection and try again.',
    );
  }
}

type Options = { method?: string; body?: unknown; signal?: AbortSignal; keepalive?: boolean };

export async function api<T>(
  path: string,
  { method = 'GET', body, signal, keepalive }: Options = {},
): Promise<T> {
  const isForm = body instanceof FormData;
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      signal,
      keepalive,
      credentials: 'same-origin',
      headers: {
        ...(body !== undefined && !isForm ? { 'Content-Type': 'application/json' } : {}),
        ...(method === 'GET' ? {} : csrfHeaders()),
      },
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError(0, 'offline', 'You appear to be offline. Check your connection and retry.');
  }
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.';
}
