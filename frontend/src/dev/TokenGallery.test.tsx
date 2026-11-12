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
import { COMPONENT_GALLERY_HASH, TOKEN_GALLERY_HASH, devRoute } from './devFlags'
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

describe('the development routes', () => {
  it('open a gallery only at its own hash', () => {
    expect(devRoute(TOKEN_GALLERY_HASH)).toBe('tokens')
    expect(devRoute(COMPONENT_GALLERY_HASH)).toBe('components')
    expect(devRoute('')).toBeNull()
    expect(devRoute('#chat')).toBeNull()
  })

  it.each(['tokens', 'components'])(
    'guard the %s page in App.tsx with the literal Vite replaces at build time',
    (route) => {
      // devRoute() alone would keep the galleries in the bundle: Rollup
      // cannot see through the function call to know the branch is dead.
      // The literal in App.tsx is what actually drops them.
      const app = readFileSync(fromSrc('App.tsx'), 'utf8')

      expect(app).toContain(`import.meta.env.DEV && devRoute() === '${route}'`)
    },
  )

  it.each(['TokenGallery', 'ComponentGallery'])(
    '%s imports its stylesheet as a string, not as a side effect',
    (name) => {
      // A plain `import './TokenGallery.css'` is a side effect Rollup keeps
      // even after it drops the module, which put the gallery's 2 kB of CSS
      // into the alpha bundle. `?inline` makes it an ordinary string export
      // that goes with the rest.
      const source = readFileSync(fromSrc('dev', `${name}.tsx`), 'utf8')

      expect(source).toContain(`from './${name}.css?inline'`)
      expect(source).not.toMatch(new RegExp(`^import '\\./${name}\\.css'$`, 'm'))
    },
  )
})
