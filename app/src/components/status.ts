// Shared colour vocabulary. Colour only carries meaning: brand (actions/selection) and status.

/** Weight of a priority, status or risk pill: `positive` filled green (closed, fine), `strong` filled ink (needs a person), `medium` outlined, `quiet` text only. */
export type Emphasis = 'positive' | 'strong' | 'medium' | 'quiet'

export type Tone = 'neutral' | 'brand' | 'ok' | 'warn' | 'danger' | 'info'

/** CSS custom property with the solid colour of a tone (dots, bars, icons). */
export function toneColor(tone: Tone): string {
  return tone === 'neutral' ? 'var(--neutral)' : `var(--${tone})`
}
