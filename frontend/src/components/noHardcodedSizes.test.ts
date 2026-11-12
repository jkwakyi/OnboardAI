/**
 * No measurement is written into a component stylesheet (ON-64).
 *
 * An acceptance criterion of the components ticket, and the sibling of the
 * colour rule in `styles/noHardcodedColours.test.ts`. A `padding: 14px`
 * typed into a component looks right on the screen of whoever typed it,
 * survives review, and then quietly does not move when the spacing scale
 * does - so the interface drifts out of alignment one component at a time.
 *
 * Ratios are not measurements and are allowed: percentages, `1fr`,
 * `aspect-ratio: 1`, a `brightness()` multiplier, an angle. What is banned
 * is an absolute or font-relative length. Anything a component genuinely
 * needs gets a token in `tokens.css`, which is where the token gallery can
 * see it and where the whole interface can change it at once.
 *
 * The rule is scoped to `components/`. The development token gallery is
 * scaffolding that never reaches a user and does set its own reading
 * widths; the shared library every page is built from does not get that
 * latitude.
 */
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { SRC_DIR } from '../test/paths'

const COMPONENTS_DIR = join(SRC_DIR, 'components')

/**
 * A number followed by a length unit.
 *
 * The leading guard keeps it off the tail of an identifier, so
 * `--space-1in-use` or a class like `.oa-card--2px` would not be read as a
 * length. Angles (`deg`, `turn`, `rad`) and time (`ms`, `s`) are absent on
 * purpose: neither is a size, and both are already tokens where they
 * matter.
 */
const LENGTH =
  /(?<![\w-])\d*\.?\d+(px|rem|em|ch|ex|vh|vw|vmin|vmax|pt|pc|cm|mm|in|q)\b/gi

/** CSS comments, which may legitimately quote a pixel value. */
const COMMENTS = /\/\*[\s\S]*?\*\//g

function stylesheets(): string[] {
  return readdirSync(COMPONENTS_DIR, { encoding: 'utf8' }).filter((entry) =>
    entry.endsWith('.css'),
  )
}

function declarations(file: string): string {
  return readFileSync(join(COMPONENTS_DIR, file), 'utf8').replace(COMMENTS, '')
}

describe('component stylesheets', () => {
  it('are there to be scanned', () => {
    // Without this, a broken walk passes everything below by scanning
    // nothing, which is the usual way a rule like this stops working.
    const files = stylesheets()

    expect(files.length).toBeGreaterThan(8)
    expect(files).toContain('Button.css')
    expect(files).toContain('accents.css')
  })

  it('contain no measurement', () => {
    const offences: string[] = []

    for (const file of stylesheets()) {
      const found = declarations(file).match(LENGTH)
      if (found !== null) {
        offences.push(`${file}: ${[...new Set(found)].join(', ')}`)
      }
    }

    expect(
      offences,
      'add a token to styles/tokens.css and refer to the custom property instead',
    ).toEqual([])
  })

  it('is a scan that would notice one', () => {
    // The inverse check. tokens.css is where lengths belong, so if the
    // pattern finds nothing there it is matching nothing anywhere and the
    // assertion above is empty.
    const tokens = readFileSync(join(SRC_DIR, 'styles', 'tokens.css'), 'utf8').replace(
      COMMENTS,
      '',
    )

    expect(tokens.match(LENGTH)?.length ?? 0).toBeGreaterThan(10)
  })

  it('are each imported by the component they belong to', () => {
    // A stylesheet nobody imports is dead weight that still passes every
    // other test in this file.
    const orphans = stylesheets().filter((file) => {
      const base = file.replace(/\.css$/, '')
      const candidates = [`${base}.tsx`, `${base}.ts`]

      return !candidates.some((candidate) => {
        try {
          return readFileSync(join(COMPONENTS_DIR, candidate), 'utf8').includes(
            `./${file}`,
          )
        } catch {
          return false
        }
      })
    })

    expect(orphans, 'these stylesheets are not imported by their component').toEqual([])
  })
})
