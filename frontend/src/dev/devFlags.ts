/**
 * Development-only entry points (ON-63, extended in ON-64).
 *
 * Two kitchen sinks, reached by hash while running `npm run dev`:
 * `#tokens` for the design tokens and `#components` for the shared
 * component library.
 *
 * `import.meta.env.DEV` is replaced with a literal `false` when Vite
 * builds, so `devRoute` collapses to `null` there and the branches in
 * `App.tsx` that call the galleries become dead code the bundler drops.
 * They are not shipped and hidden - they are not shipped.
 */

export const TOKEN_GALLERY_HASH = '#tokens'
export const COMPONENT_GALLERY_HASH = '#components'

const ROUTES = {
  [TOKEN_GALLERY_HASH]: 'tokens',
  [COMPONENT_GALLERY_HASH]: 'components',
} as const

export type DevRoute = (typeof ROUTES)[keyof typeof ROUTES]

/** Which development page the hash asks for, if any. */
export function devRoute(hash: string = window.location.hash): DevRoute | null {
  if (!import.meta.env.DEV) {
    return null
  }

  return ROUTES[hash as keyof typeof ROUTES] ?? null
}
