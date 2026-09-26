const dateTime = new Intl.DateTimeFormat('tr-TR', {dateStyle: 'medium', timeStyle: 'short'});
const number = new Intl.NumberFormat('tr-TR');

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? '—' : dateTime.format(parsed);
}

export function formatNumber(value: number): string {
  return number.format(value);
}
