/**
 * `tokens.css` is the only place a colour is written down (ON-63).
 *
 * An acceptance criterion of the tokens ticket, and the one most likely to
 * rot: a hard-coded colour is quick to type, looks right on the screen of
 * whoever typed it, and is invisible in review. It only shows up later, when
 * a token changes and one corner of the interface does not follow.
 *
 * Test files are exempt because a test may legitimately name the value it is
 * checking - this file itself contains hex patterns.
 */
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { SRC_DIR } from '../test/paths'

/** The one file allowed to contain colour literals. */
const TOKENS_FILE = 'styles/tokens.css'

const SCANNED_EXTENSIONS = ['.css', '.ts', '.tsx']

const COLOUR_PATTERNS: { name: string; pattern: RegExp }[] = [
  { name: 'hex colour', pattern: /#[0-9a-f]{3,8}\b/gi },
  { name: 'rgb()/rgba() literal', pattern: /\brgba?\(\s*\d/gi },
  { name: 'hsl()/hsla() literal', pattern: /\bhsla?\(\s*[\d.]/gi },
  {
    name: 'named colour',
    pattern:
      /:\s*(white|black|red|green|blue|grey|gray|silver|navy|teal|orange|purple|yellow)\s*[;,)]/gi,
  },
]

function sourceFiles(): string[] {
  return readdirSync(SRC_DIR, { recursive: true, encoding: 'utf8' })
    .filter((entry) => SCANNED_EXTENSIONS.some((ext) => entry.endsWith(ext)))
    .filter((entry) => !/\.test\.[cm]?tsx?$/.test(entry))
    .map((entry) => entry.replace(/\\/g, '/'))
}

describe('colour literals', () => {
  it('finds the files it is meant to be scanning', () => {
    // Without this, a broken walk would pass every assertion below by
    // scanning nothing at all.
    const files = sourceFiles()
    expect(files.length).toBeGreaterThan(3)
    expect(files).toContain('styles/base.css')
    expect(files).toContain('dev/TokenGallery.css')
  })

  it('appear nowhere but tokens.css', () => {
    const offences: string[] = []

    for (const file of sourceFiles()) {
      if (file === TOKENS_FILE) {
        continue
      }

      const source = readFileSync(join(SRC_DIR, file), 'utf8')
      for (const { name, pattern } of COLOUR_PATTERNS) {
        const found = source.match(pattern)
        if (found !== null) {
          offences.push(`${file}: ${name} ${found.join(', ')}`)
        }
      }
    }

    expect(
      offences,
      'move these into tokens.css and refer to the custom property instead',
    ).toEqual([])
  })

  it('does appear in tokens.css, which is where they belong', () => {
    // The inverse check: if this ever fails, the scan above is matching
    // nothing and is not protecting anything.
    const source = readFileSync(join(SRC_DIR, TOKENS_FILE), 'utf8')
    expect(source).toMatch(/#[0-9a-f]{6}\b/i)
  })
})
