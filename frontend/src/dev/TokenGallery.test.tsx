/**
 * The token gallery shows every token, and ships in no build (ON-63).
 *
 * jsdom loads no stylesheet, so nothing here can assert what a token looks
 * like - `tokens.test.ts` checks the values. What these check is that the
 * page lists every token the manifest claims, and that the gallery stays
 * behind the development flag.
 */
import { readFileSync } from 'node:fs'

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import TokenGallery from './TokenGallery'
import { GALLERY_TOKENS, TOKEN_GROUPS } from './tokenManifest'
import { TOKEN_GALLERY_HASH, isTokenGalleryEnabled } from './devFlags'
import { fromSrc } from '../test/paths'

describe('the token gallery', () => {
  it('names every token in the manifest', () => {
    render(<TokenGallery />)

    for (const token of GALLERY_TOKENS) {
      expect(screen.getByText(token), `${token} is not on the page`).toBeInTheDocument()
    }
  })

  it('groups them under headings', () => {
    render(<TokenGallery />)

    for (const group of TOKEN_GROUPS) {
      expect(screen.getByRole('heading', { name: group.title })).toBeInTheDocument()
    }
  })

  it('offers a control of each kind so the focus ring can be checked', () => {
    render(<TokenGallery />)

    expect(screen.getByRole('button', { name: 'Button' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Example input' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Link' })).toBeInTheDocument()
  })

  it('uses no image or icon asset', () => {
    // Epic ON-62: original design, no third-party template assets.
    const { container } = render(<TokenGallery />)

    expect(container.querySelectorAll('img, svg')).toHaveLength(0)
  })
})

describe('the development flag', () => {
  it('opens the gallery only at its own hash', () => {
    expect(isTokenGalleryEnabled(TOKEN_GALLERY_HASH)).toBe(true)
    expect(isTokenGalleryEnabled('')).toBe(false)
    expect(isTokenGalleryEnabled('#chat')).toBe(false)
  })

  it('is guarded in App.tsx by the literal Vite replaces at build time', () => {
    // isTokenGalleryEnabled alone would keep the gallery in the bundle:
    // Rollup cannot see through the function call to know the branch is
    // dead. The literal in App.tsx is what actually drops it.
    const app = readFileSync(fromSrc('App.tsx'), 'utf8')

    expect(app).toContain('import.meta.env.DEV && isTokenGalleryEnabled()')
  })

  it('imports its stylesheet as a string, not as a side effect', () => {
    // A plain `import './TokenGallery.css'` is a side effect Rollup keeps
    // even after it drops this module, which put the gallery's 2 kB of CSS
    // into the alpha bundle. `?inline` makes it an ordinary string export
    // that goes with the rest.
    const gallery = readFileSync(fromSrc('dev', 'TokenGallery.tsx'), 'utf8')

    expect(gallery).toContain("from './TokenGallery.css?inline'")
    expect(gallery).not.toMatch(/^import '\.\/TokenGallery\.css'$/m)
  })
})
