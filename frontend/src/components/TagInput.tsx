import { X } from 'lucide-react';
import { useState, type KeyboardEvent } from 'react';
import { Input } from './ui/form';

/** Text box that turns entries into removable tags. Enter or comma adds one. */
export function TagInput({
  values,
  onChange,
  suggestions = [],
  placeholder,
  itemName = 'skill',
  ...ids
}: {
  values: string[];
  onChange: (values: string[]) => void;
  suggestions?: string[];
  placeholder?: string;
  itemName?: string;
  id?: string;
  'aria-describedby'?: string;
  'aria-invalid'?: boolean;
}) {
  const [draft, setDraft] = useState('');
  const listId = ids.id ? `${ids.id}-list` : undefined;

  const add = (raw: string) => {
    const fresh = raw
      .split(',')
      .map((part) => part.trim())
      .filter((part) => part && !values.some((v) => v.toLowerCase() === part.toLowerCase()));
    if (fresh.length) onChange([...values, ...fresh]);
    setDraft('');
  };

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Enter' && draft.trim()) {
      event.preventDefault();
      add(draft);
    } else if (event.key === 'Backspace' && !draft && values.length) {
      onChange(values.slice(0, -1));
    }
  };

  return (
    <div className="flex flex-col gap-2">
      {values.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {values.map((value) => (
            <li
              key={value}
              className="bg-secondary text-secondary-foreground flex items-center gap-1 rounded-full py-0.5 pr-1 pl-3 text-sm"
            >
              {value}
              <button
                type="button"
                aria-label={`Remove ${value}`}
                className="hover:bg-border flex size-7 items-center justify-center rounded-full"
                onClick={() => onChange(values.filter((v) => v !== value))}
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      <Input
        {...ids}
        value={draft}
        list={suggestions.length ? listId : undefined}
        placeholder={placeholder ?? `Type a ${itemName} and press Enter`}
        onChange={(e) => {
          const { value } = e.target;
          if (value.includes(',')) add(value);
          else setDraft(value);
        }}
        onKeyDown={onKeyDown}
        onBlur={() => draft.trim() && add(draft)}
      />
      {suggestions.length > 0 && (
        <datalist id={listId}>
          {suggestions.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      )}
    </div>
  );
}
