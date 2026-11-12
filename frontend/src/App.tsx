/**
 * Application shell placeholder.
 *
 * The real shell is ON-65, built on the design tokens from ON-63 and the
 * shared components from ON-64. Nothing here styles anything, so that the
 * tokens ticket owns the first visual decision.
 */
import ComponentGallery from './dev/ComponentGallery'
import { devRoute } from './dev/devFlags'
import TokenGallery from './dev/TokenGallery'

function App() {
  // The literal `import.meta.env.DEV` has to appear in each branch, not
  // only inside devRoute: Vite replaces it with `false` when it builds, the
  // branch becomes dead code, and the gallery is dropped from the bundle
  // rather than shipped and hidden. A test checks both guards are still
  // here, because without them the pages ship.
  if (import.meta.env.DEV && devRoute() === 'tokens') {
    return <TokenGallery />
  }

  if (import.meta.env.DEV && devRoute() === 'components') {
    return <ComponentGallery />
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
