/**
 * The design tokens are complete, documented and readable (ON-63).
 *
 * These read `tokens.css` as text rather than through the browser, because
 * the unit tests run in jsdom, which applies no stylesheet. Reading the file
 * is also the stricter check: it sees what was written, not what a browser
 * was willing to make of it.
 *
 * The contrast assertions are the ones that matter. A dark theme is easy to
 * draw and easy to make unreadable, and the failure is invisible to anyone
 * with good eyesight and a good monitor - exactly the people who build it.
 */
import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { GALLERY_TOKENS, INTERNAL_TOKENS } from '../dev/tokenManifest'
import { fromSrc } from '../test/paths'

const TOKENS_CSS = readFileSync(fromSrc('styles', 'tokens.css'), 'utf8')

/**
 * Every custom property declared in the file, first declaration wins.
 *
 * The reduced-motion block redeclares --transition-duration; the first one
 * is the value components get by default, which is what these tests are
 * about.
 */
function declaredTokens(css: string): Map<string, string> {
  const tokens = new Map<string, string>()
  const pattern = /^\s*(--[a-z0-9-]+)\s*:\s*([^;]+);/gm
  let match = pattern.exec(css)
  while (match !== null) {
    if (!tokens.has(match[1])) {
      tokens.set(match[1], match[2].trim())
    }
    match = pattern.exec(css)
  }
  return tokens
}

const TOKENS = declaredTokens(TOKENS_CSS)

/**
 * A token's colour as RGB channels.
 *
 * Handles the two forms the file uses: a hex literal, and `rgb(var(--x-rgb))`
 * built from a channel triple. Anything else is a colour this helper was not
 * written for, and saying so beats silently returning black.
 */
function channels(token: string): [number, number, number] {
  const value = TOKENS.get(token)
  if (value === undefined) {
    throw new Error(`${token} is not declared in tokens.css`)
  }

  const hex = /^#([0-9a-f]{6})$/i.exec(value)
  if (hex !== null) {
    const digits = hex[1]
    return [
      Number.parseInt(digits.slice(0, 2), 16),
      Number.parseInt(digits.slice(2, 4), 16),
      Number.parseInt(digits.slice(4, 6), 16),
    ]
  }

  const reference = /^rgb\(var\((--[a-z0-9-]+)\)\)$/.exec(value)
  if (reference !== null) {
    const triple = TOKENS.get(reference[1])
    if (triple === undefined) {
      throw new Error(`${token} refers to ${reference[1]}, which is not declared`)
    }
    const parts = triple.split(/\s+/).map(Number)
    if (parts.length !== 3 || parts.some(Number.isNaN)) {
      throw new Error(`${reference[1]} is not three channel values: ${triple}`)
    }
    return [parts[0], parts[1], parts[2]]
  }

  throw new Error(`${token} is not a colour this test can read: ${value}`)
}

/** WCAG 2.1 relative luminance. */
function luminance(token: string): number {
  const [r, g, b] = channels(token).map((channel) => {
    const c = channel / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** WCAG 2.1 contrast ratio, 1 to 21. */
function contrast(a: string, b: string): number {
  const [lighter, darker] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (lighter + 0.05) / (darker + 0.05)
}

const SURFACES = ['--bg', '--surface-1', '--surface-2']

/** Colours that can carry text, and so owe 4.5:1 on every surface. */
const TEXT_COLOURS = [
  '--text',
  '--text-muted',
  '--accent-chat',
  '--accent-documents',
  '--accent-escalations',
  '--accent-info',
  '--success',
  '--warning',
  '--danger',
]

describe('the token file', () => {
  it('declares every colour the design calls for', () => {
    for (const token of [
      '--bg',
      '--surface-1',
      '--surface-2',
      '--border',
      '--text',
      '--text-muted',
      '--accent-chat',
      '--accent-documents',
      '--accent-escalations',
      '--accent-info',
      '--success',
      '--warning',
      '--danger',
    ]) {
      expect(TOKENS.has(token), `${token} is missing`).toBe(true)
    }
  })

  it('gives every accent and status colour a soft variant', () => {
    for (const token of [
      '--accent-chat',
      '--accent-documents',
      '--accent-escalations',
      '--accent-info',
      '--success',
      '--warning',
      '--danger',
    ]) {
      expect(TOKENS.has(`${token}-soft`), `${token}-soft is missing`).toBe(true)
    }
  })

  it('declares the spacing, radius and type scales', () => {
    for (const token of [
      '--space-1',
      '--space-2',
      '--space-3',
      '--space-4',
      '--space-5',
      '--space-6',
      '--space-7',
      '--radius-input',
      '--radius-card',
      '--radius-pill',
      '--border-width',
      '--shadow-raised',
      '--font-sans',
      '--text-xs',
      '--text-sm',
      '--text-md',
      '--text-lg',
      '--text-xl',
      '--weight-regular',
      '--weight-medium',
      '--weight-semibold',
      '--transition-duration',
    ]) {
      expect(TOKENS.has(token), `${token} is missing`).toBe(true)
    }
  })

  it('sets the section label to 12px uppercase with wide tracking', () => {
    expect(TOKENS.get('--label-size')).toBe('var(--text-xs)')
    expect(TOKENS.get('--text-xs')).toContain('0.75rem')
    expect(TOKENS.get('--label-tracking')).toBe('0.12em')
  })

  it('turns transitions off under prefers-reduced-motion', () => {
    expect(TOKENS_CSS).toMatch(/@media \(prefers-reduced-motion: reduce\)/)
    const reduced = TOKENS_CSS.slice(
      TOKENS_CSS.indexOf('@media (prefers-reduced-motion: reduce)'),
    )
    expect(reduced).toMatch(/--transition-duration:\s*0ms/)
  })

  it('downloads no webfont', () => {
    expect(TOKENS_CSS).not.toMatch(/@font-face|fonts\.googleapis|url\(/)
    expect(TOKENS.get('--font-sans')).toContain('system-ui')
  })
})

describe('contrast', () => {
  it.each(TEXT_COLOURS)('%s reaches AA for body text on every surface', (colour) => {
    for (const surface of SURFACES) {
      const ratio = contrast(colour, surface)
      expect(
        ratio,
        `${colour} on ${surface} is ${ratio.toFixed(2)}:1, below the 4.5:1 AA threshold`,
      ).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('gives a control a boundary that meets non-text contrast', () => {
    // WCAG 1.4.11 asks 3:1 of anything needed to identify a control. --border
    // is a hairline between surfaces and is far below that on purpose, which
    // is why --border-strong exists for the edge of an input.
    for (const surface of SURFACES) {
      const ratio = contrast('--border-strong', surface)
      expect(
        ratio,
        `--border-strong on ${surface} is ${ratio.toFixed(2)}:1, below 3:1`,
      ).toBeGreaterThanOrEqual(3)
    }
  })

  it('keeps the focus ring visible on every surface', () => {
    expect(TOKENS.get('--focus-ring-color')).toBe('var(--accent-info)')
    for (const surface of SURFACES) {
      expect(contrast('--accent-info', surface)).toBeGreaterThanOrEqual(3)
    }
  })
})

describe('the token gallery manifest', () => {
  it('accounts for every token in the file', () => {
    const shown = new Set([...GALLERY_TOKENS, ...INTERNAL_TOKENS])
    const missing = [...TOKENS.keys()].filter((token) => !shown.has(token))

    expect(
      missing,
      'these tokens exist but the gallery neither shows them nor lists them as internal',
    ).toEqual([])
  })

  it('shows nothing that is not in the file', () => {
    const unknown = GALLERY_TOKENS.filter((token) => !TOKENS.has(token))

    expect(unknown, 'the gallery lists tokens that no longer exist').toEqual([])
  })

  it('lists each token once', () => {
    expect(GALLERY_TOKENS).toHaveLength(new Set(GALLERY_TOKENS).size)
  })
})
