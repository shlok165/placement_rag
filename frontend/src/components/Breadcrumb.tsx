import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router';

export function Breadcrumb({ items, current }: { items: [string, string][]; current: string }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-2">
      <ol className="text-muted-foreground flex flex-wrap items-center gap-1 text-sm">
        {items.map(([to, label]) => (
          <li key={to} className="flex items-center gap-1">
            <Link
              to={to}
              className="hover:text-foreground rounded-sm py-1 underline-offset-4 hover:underline"
            >
              {label}
            </Link>
            <ChevronRight className="size-3.5" aria-hidden />
          </li>
        ))}
        <li aria-current="page" className="text-foreground max-w-72 truncate">
          {current}
        </li>
      </ol>
    </nav>
  );
}
