import { Check } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { Logo } from '@/components/Logo';

const points = [
  'Search by meaning, and see exactly why a posting fits you',
  'A copilot that answers only from real postings, with sources',
  'Track every application, deadline and reminder in one place',
];

export function AuthLayout({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <main className="flex flex-col justify-center px-4 py-10 sm:px-8">
        <div className="mx-auto w-full max-w-sm">
          <Link to="/welcome" className="mb-8 inline-block rounded-md lg:hidden">
            <Logo />
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {description && <p className="text-muted-foreground mt-1.5">{description}</p>}
          <div className="mt-7">{children}</div>
          {footer && <p className="text-muted-foreground mt-8 text-sm">{footer}</p>}
        </div>
      </main>
      <aside
        aria-label="About placement_rag"
        className="bg-primary text-primary-foreground relative hidden overflow-hidden p-10 lg:order-first lg:flex lg:flex-col"
      >
        <Link to="/welcome" className="w-fit rounded-md [&_rect]:fill-white/15">
          <Logo />
        </Link>
        <div className="my-auto max-w-md">
          <p className="text-3xl leading-tight font-semibold tracking-tight">
            Find the internship that fits, and know why it does.
          </p>
          <ul className="mt-8 flex flex-col gap-4">
            {points.map((point) => (
              <li key={point} className="flex gap-3 text-base opacity-90">
                <Check className="mt-0.5 size-5 shrink-0" aria-hidden />
                {point}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-sm">Built for the CAPS office at IIT Ropar.</p>
        <div
          aria-hidden
          className="pointer-events-none absolute -right-24 -bottom-24 size-72 rounded-full bg-white/10"
        />
      </aside>
    </div>
  );
}
