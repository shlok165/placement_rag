import type { ReactNode } from 'react';
import { Logo } from '@/components/Logo';
import { Card } from '@/components/ui/display';

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
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center gap-6 px-4 py-8">
      <div className="flex flex-col items-center gap-3 text-center">
        <Logo />
        <p className="text-muted-foreground text-sm">
          Internships and placements at IIT Ropar, with a copilot that only answers from real
          postings.
        </p>
      </div>
      <Card className="p-6">
        <h1 className="text-xl font-semibold">{title}</h1>
        {description && <p className="text-muted-foreground mt-1 text-sm">{description}</p>}
        <div className="mt-5">{children}</div>
      </Card>
      {footer && <p className="text-muted-foreground text-center text-sm">{footer}</p>}
    </main>
  );
}
