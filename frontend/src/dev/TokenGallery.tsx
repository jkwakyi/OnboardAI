/**
 * The kitchen sink: every design token, rendered (ON-63).
 *
 * Development only. `isTokenGalleryEnabled` is false in a production build,
 * and Vite replaces `import.meta.env.DEV` with `false` there, so this module
 * is dead code the bundler drops - a test asserts it is absent from `dist`.
 *
 * The point of the page is that it reads the tokens from the live stylesheet
 * rather than repeating their values, so a token that is renamed or removed
 * shows up here as an empty row instead of a stale swatch.
 */
import { useEffect, useState } from 'react'

import {
  GALLERY_TOKENS,
  TOKEN_GROUPS,
  type TokenGroup,
  type TokenPreview,
} from './tokenManifest'
// Imported as a string rather than for its side effect. A plain CSS import
// is a side effect Rollup must keep even after it drops this module, which
// left the gallery's stylesheet in the production bundle; a string export is
// tree-shaken with everything else. Verified by grepping dist/.
import galleryStyles from './TokenGallery.css?inline'

const SAMPLE_TEXT = 'Onboarding starts here'

/**
 * The computed value of every token, read from `:root`.
 *
 * Read in an effect rather than during render because the stylesheet is not
 * guaranteed to be applied on the first pass. In a jsdom test no stylesheet
 * is loaded at all and every value is empty, which is why the markup below
 * never depends on one being present.
 */
function useTokenValues(): Record<string, string> {
  const [values, setValues] = useState<Record<string, string>>({})

  useEffect(() => {
    const computed = getComputedStyle(document.documentElement)
    const next: Record<string, string> = {}
    for (const token of GALLERY_TOKENS) {
      next[token] = computed.getPropertyValue(token).trim()
    }
    setValues(next)
  }, [])

  return values
}

function Preview({ token, kind }: { token: string; kind: TokenPreview }) {
  const value = 'var(' + token + ')'

  switch (kind) {
    case 'color':
      return <span className="gallery-swatch" style={{ background: value }} />
    case 'space':
      return <span className="gallery-bar" style={{ width: value }} />
    case 'radius':
      return <span className="gallery-shape" style={{ borderRadius: value }} />
    case 'shadow':
      return <span className="gallery-shape" style={{ boxShadow: value }} />
    case 'font-family':
      return (
        <span className="gallery-sample" style={{ fontFamily: value }}>
          {SAMPLE_TEXT}
        </span>
      )
    case 'font-size':
      return (
        <span className="gallery-sample" style={{ fontSize: value }}>
          {SAMPLE_TEXT}
        </span>
      )
    case 'font-weight':
      return (
        <span className="gallery-sample" style={{ fontWeight: value }}>
          {SAMPLE_TEXT}
        </span>
      )
    case 'value':
      return null
  }
}

function Group({ group, values }: { group: TokenGroup; values: Record<string, string> }) {
  const headingId = 'group-' + group.title.toLowerCase().replace(/\s+/g, '-')

  return (
    <section className="gallery-group" aria-labelledby={headingId}>
      <h2 className="section-label" id={headingId}>
        {group.title}
      </h2>
      <p className="gallery-note">{group.note}</p>
      <dl className="gallery-rows">
        {group.tokens.map((token) => (
          <div className="gallery-row" key={token}>
            <dt className="gallery-name">
              <code>{token}</code>
            </dt>
            <dd className="gallery-value">
              <Preview token={token} kind={group.preview} />
              <span className="gallery-computed">{values[token] || 'not set'}</span>
            </dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

export default function TokenGallery() {
  const values = useTokenValues()

  return (
    <main className="gallery">
      <style>{galleryStyles}</style>
      <header className="gallery-header">
        <h1>Design tokens</h1>
        <p className="gallery-note">
          Every custom property the interface is built from, read from the live
          stylesheet. Development only: this page is not in the alpha build.
        </p>
      </header>
      {TOKEN_GROUPS.map((group) => (
        <Group group={group} key={group.title} values={values} />
      ))}
      <section className="gallery-group" aria-labelledby="group-focus-demo">
        <h2 className="section-label" id="group-focus-demo">
          Focus ring, in use
        </h2>
        <p className="gallery-note">
          Tab to each control. The ring appears for the keyboard and not for a
          mouse click, because it is bound to <code>:focus-visible</code>.
        </p>
        <div className="gallery-controls">
          <button type="button">Button</button>
          <input aria-label="Example input" placeholder="Input" />
          <a href="#tokens">Link</a>
        </div>
      </section>
    </main>
  )
}
