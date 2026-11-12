/**
 * Application shell placeholder.
 *
 * The real shell is ON-65, built on the design tokens from ON-63 and the
 * shared components from ON-64. Nothing here styles anything, so that the
 * tokens ticket owns the first visual decision.
 */
import { isTokenGalleryEnabled } from './dev/devFlags'
import TokenGallery from './dev/TokenGallery'

function App() {
  // The literal `import.meta.env.DEV` has to appear here, not only inside
  // isTokenGalleryEnabled: Vite replaces it with `false` when it builds, the
  // branch becomes dead code, and the gallery is dropped from the bundle
  // rather than shipped and hidden. A test checks the guard is still here.
  if (import.meta.env.DEV && isTokenGalleryEnabled()) {
    return <TokenGallery />
  }

  return (
    <main>
      <h1>OnboardAI</h1>
      <p>AI employee onboarding assistant.</p>
      <p>
        The interface is built in epic ON-62: design tokens (ON-63), shared
        components (ON-64), app shell (ON-65), then the pages.
      </p>
    </main>
  )
}

export default App
