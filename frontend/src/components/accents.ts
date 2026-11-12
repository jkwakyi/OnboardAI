/**
 * The section accents (ON-63), as something a component can take as a prop.
 *
 * A component that accepts an `accent` puts `accentClass(accent)` in its
 * class list and then styles itself with `var(--accent)` and
 * `var(--accent-soft)`. The mapping from "which area of the app is this" to
 * "which colour" lives in one stylesheet instead of in a switch statement
 * inside every component, and a component never names a colour at all.
 */
import './accents.css'

export const ACCENTS = ['chat', 'documents', 'escalations', 'info'] as const

export type Accent = (typeof ACCENTS)[number]

export function accentClass(accent: Accent): string {
  return `oa-accent-${accent}`
}
