import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import axe from 'axe-core';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { vi } from 'vitest';
import { TooltipProvider } from '@/components/ui/overlay';

export type MockRoutes = Record<string, unknown>;

/** Serves canned JSON for `METHOD /path`. An ApiMock value sets status and body. */
export function mockApi(routes: MockRoutes) {
  const calls: { key: string; body: unknown }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace('/api', '').split('?')[0];
    const key = `${init?.method ?? 'GET'} ${path}`;
    calls.push({ key, body: typeof init?.body === 'string' ? JSON.parse(init.body) : init?.body });
    const value = routes[key];
    if (value === undefined) {
      return Response.json({ error: { code: 'not_found', message: key } }, { status: 404 });
    }
    if (value instanceof Response) return value.clone();
    return Response.json(value);
  });
  vi.stubGlobal('fetch', fetchMock);
  return calls;
}

export function renderPage(ui: ReactNode, path = '/', { tour = false } = {}) {
  if (!tour) localStorage.setItem('tour-seen', '1');
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

export async function axeViolations(container: HTMLElement) {
  const results = await axe.run(container, {
    rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
  });
  return results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(' | ')}`);
}

export const studentUser = {
  id: 1,
  email: 'asha@example.com',
  full_name: 'Asha Demo',
  role: 'student',
  consent_at: '2026-01-01T00:00:00Z',
  onboarded_at: '2026-01-01T00:00:00Z',
};

export const coordinatorUser = { ...studentUser, id: 2, role: 'coordinator' };
