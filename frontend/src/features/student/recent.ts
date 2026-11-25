const KEY = 'recent-searches';
const LIMIT = 5;

/** Recent searches stay in this browser and are never sent to the server. */
export function readRecent(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) ?? '[]');
    return Array.isArray(value) ? value.filter((v) => typeof v === 'string').slice(0, LIMIT) : [];
  } catch {
    return [];
  }
}

export function addRecent(query: string): string[] {
  const next = [query, ...readRecent().filter((q) => q !== query)].slice(0, LIMIT);
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Not being able to store recent searches is harmless.
  }
  return next;
}

export function clearRecent() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    // Nothing stored, nothing to clear.
  }
}
