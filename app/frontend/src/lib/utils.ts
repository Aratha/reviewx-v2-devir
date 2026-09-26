export function classes(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(' ');
}

/** Semantic colour intents shared by badges and status markers. */
export type Tone = 'neutral' | 'primary' | 'success' | 'danger' | 'warning' | 'info';
