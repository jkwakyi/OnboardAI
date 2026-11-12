/**
 * No measurement is written into a shipped stylesheet (ON-64, ON-65).
 *
 * The sibling of the colour rule next door. A `padding: 14px` typed into a
 * component looks right on the screen of whoever typed it, survives
 * review, and then quietly does not move when the spacing scale does — so
 * the interface drifts out of alignment one component at a time.
 *
 * Ratios are not measurements and are allowed: percentages, `1fr`,
 * `aspect-ratio: 1`, a `brightness()` multiplier, an angle. What is banned
 * is an absolute or font-relative length. Anything a component genuinely
 * needs gets a token in `tokens.css`, which is where the token gallery can
 * see it and where the whole interface can change it at once.
 *
 * The rule covers the shared library and the application shell — the two
 * places whose stylesheets ship. The development galleries under `dev/`
 * are scaffolding that never reaches a user and do set their own reading
 * widths; the interface everyone else is built from does not get that
 * latitude.
 */
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { SRC_DIR } from '../test/paths'

/** The directories whose stylesheets ship. */
const SCANNED_DIRS = ['components', 'shell']

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
  /(?<![\w-])\d*\.?\d+(px|rem|em|ch|ex|vh|vw|dvh|dvw|svh|svw|lvh|lvw|vmin|vmax|pt|pc|cm|mm|in|q)\b/gi

/**
 * The whole viewport is not a size anybody chose.
 *
 * A shell that fills the screen has to say so somehow, and `--full-height:
 * 100dvh` would be a token that means "the screen" - a name for something
 * that already has one. Any other fraction of the viewport is a design
 * value and gets no exemption: `80vh` for a panel is a decision, `100dvh`
 * is a fact about the window.
 */
const FULL_VIEWPORT = /^100(vh|vw|dvh|dvw|svh|svw|lvh|lvw)$/i

/** CSS comments, which may legitimately quote a pixel value. */
const COMMENTS = /\/\*[\s\S]*?\*\//g

/** Every shipped stylesheet, as a path relative to `src/`. */
function stylesheets(): string[] {
  return SCANNED_DIRS.flatMap((dir) =>
    readdirSync(join(SRC_DIR, dir), { encoding: 'utf8' })
      .filter((entry) => entry.endsWith('.css'))
      .map((entry) => `${dir}/${entry}`),
  )
}

function declarations(file: string): string {
  return readFileSync(join(SRC_DIR, file), 'utf8').replace(COMMENTS, '')
}

describe('shipped stylesheets', () => {
  it('are there to be scanned', () => {
    // Without this, a broken walk passes everything below by scanning
    // nothing, which is the usual way a rule like this stops working.
    const files = stylesheets()

    expect(files.length).toBeGreaterThan(10)
    expect(files).toContain('components/Button.css')
    expect(files).toContain('components/accents.css')
    expect(files).toContain('shell/AppShell.css')
  })

  it('contain no measurement', () => {
    const offences: string[] = []

    for (const file of stylesheets()) {
      const found = (declarations(file).match(LENGTH) ?? []).filter(
        (length) => !FULL_VIEWPORT.test(length),
      )
      if (found.length > 0) {
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

  it('exempts the whole viewport and nothing smaller', () => {
    // The exemption is narrow on purpose. Without this, widening it later
    // to "any viewport unit" would go unnoticed and let a chosen fraction
    // of the screen into a stylesheet.
    const offending = (css: string) =>
      (css.match(LENGTH) ?? []).filter((length) => !FULL_VIEWPORT.test(length))

    expect(offending('height: 100dvh;')).toEqual([])
    expect(offending('height: 100vh;')).toEqual([])
    expect(offending('max-height: 80vh;')).toEqual(['80vh'])
    expect(offending('width: 50vw;')).toEqual(['50vw'])
  })

  it('are each imported by the module they belong to', () => {
    // A stylesheet nobody imports is dead weight that still passes every
    // other test in this file.
    const orphans = stylesheets().filter((file) => {
      const [dir, name] = file.split('/')
      const base = name.replace(/\.css$/, '')

      return ![`${base}.tsx`, `${base}.ts`].some((candidate) => {
        try {
          return readFileSync(join(SRC_DIR, dir, candidate), 'utf8').includes(`./${name}`)
        } catch {
          return false
        }
      })
    })

    expect(orphans, 'these stylesheets are not imported by their module').toEqual([])
  })
})
