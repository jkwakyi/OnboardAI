/**
 * The application (ON-65).
 *
 * Everything signed-in renders inside the shell; the login page renders
 * outside it. Both are wired up in `shell/AppRoutes.tsx`.
 */
import ComponentGallery from './dev/ComponentGallery'
import { devRoute } from './dev/devFlags'
import TokenGallery from './dev/TokenGallery'
import AppRoutes from './shell/AppRoutes'

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

  return <AppRoutes />
}

export default App
