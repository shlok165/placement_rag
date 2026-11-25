import Markdown from 'react-markdown';
import { Link } from 'react-router';
import remarkGfm from 'remark-gfm';
import type { Citation } from '@/lib/types';

/** Turns `[#12]` markers into links, which are rendered as citation chips. */
export function linkCitations(text: string): string {
  return text.replace(/\[#(\d+)\]/g, '[#$1](/jobs/$1)');
}

const chip =
  'bg-accent text-accent-foreground mx-0.5 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium no-underline hover:underline';

export function Answer({ text, citations }: { text: string; citations: Citation[] }) {
  const titles = new Map(citations.map((c) => [String(c.job_id), `${c.title} at ${c.company}`]));
  return (
    <div className="prose-chat text-sm leading-relaxed break-words">
      <Markdown
        remarkPlugins={[remarkGfm]}
        allowedElements={[
          'p',
          'strong',
          'em',
          'ul',
          'ol',
          'li',
          'a',
          'code',
          'table',
          'thead',
          'tbody',
          'tr',
          'th',
          'td',
          'h3',
          'br',
        ]}
        unwrapDisallowed
        components={{
          a: ({ href, children }) => {
            const id = href?.match(/^\/jobs\/(\d+)$/)?.[1];
            if (!id) return <>{children}</>;
            return (
              <Link to={href!} className={chip} title={titles.get(id)}>
                <span className="sr-only">{titles.get(id) ?? 'Posting'} </span>
                {children}
              </Link>
            );
          },
          table: ({ children }) => (
            <div className="overflow-x-auto" role="region" aria-label="Comparison" tabIndex={0}>
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {linkCitations(text)}
      </Markdown>
    </div>
  );
}
