import type { ReactNode } from 'react';

export type BarItem = { key: string; label: ReactNode; value: number; note?: string };

/**
 * Horizontal bars for one measure. Every bar carries its value as text, so the list reads the same
 * without the bars.
 */
export function BarList({
  items,
  caption,
  valueLabel,
}: {
  items: BarItem[];
  caption: string;
  valueLabel: string;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">{caption}</caption>
      <thead className="sr-only">
        <tr>
          <th scope="col">Item</th>
          <th scope="col">{valueLabel}</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr
            key={item.key}
            className="hover:bg-muted"
            title={item.note ?? `${item.value} ${valueLabel}`}
          >
            <th scope="row" className="w-full py-2 pr-4 text-left font-normal">
              <span className="block">{item.label}</span>
              <span
                aria-hidden
                className="bg-primary mt-1 block h-1.5 rounded-r"
                style={{ width: `${(item.value / max) * 100}%` }}
              />
            </th>
            <td className="tabular py-2 pl-2 text-right align-top font-medium">
              {item.value.toLocaleString('en-IN')}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="bg-card rounded-lg border p-4 shadow-sm">
      <p className="text-muted-foreground text-sm">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      {hint && <p className="text-muted-foreground mt-1 text-xs">{hint}</p>}
    </div>
  );
}
