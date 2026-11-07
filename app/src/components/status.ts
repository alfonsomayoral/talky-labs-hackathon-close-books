// Shared colour vocabulary. Colour only carries meaning: brand (actions/selection) and status.

/** Weight of a priority, status or risk pill: filled, outlined or text only (deep green, never a status colour). */
export type Emphasis = 'strong' | 'medium' | 'quiet'

export type Tone = 'neutral' | 'brand' | 'ok' | 'warn' | 'danger' | 'info'

/** CSS custom property with the solid colour of a tone (dots, bars, icons). */
export function toneColor(tone: Tone): string {
  return tone === 'neutral' ? 'var(--neutral)' : `var(--${tone})`
}
