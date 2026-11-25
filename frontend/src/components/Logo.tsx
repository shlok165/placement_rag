export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="size-8" aria-hidden>
        <rect width="32" height="32" rx="7" className="fill-primary" />
        <path
          d="M9 21.5V10.5h6.2a3.9 3.9 0 0 1 0 7.8H12"
          fill="none"
          className="stroke-primary-foreground"
          strokeWidth="2.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="22.2" cy="20.6" r="2.4" className="fill-primary-foreground opacity-70" />
      </svg>
      {!compact && <span className="text-lg font-semibold tracking-tight">placement_rag</span>}
    </span>
  );
}
