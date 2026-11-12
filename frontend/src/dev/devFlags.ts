/**
 * Development-only entry points (ON-63).
 *
 * The token gallery is reached at `#tokens` while running `npm run dev`.
 * `import.meta.env.DEV` is replaced with a literal `false` when Vite builds,
 * so the check below collapses and the gallery is dropped from the bundle
 * rather than merely hidden in it.
 */

/** The hash that opens the token gallery during development. */
export const TOKEN_GALLERY_HASH = '#tokens'

export function isTokenGalleryEnabled(hash: string = window.location.hash): boolean {
  return import.meta.env.DEV && hash === TOKEN_GALLERY_HASH
}
