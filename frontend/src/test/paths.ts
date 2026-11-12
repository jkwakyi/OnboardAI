/**
 * Where the source tree is, for tests that read files rather than render.
 *
 * `import.meta.url` is not a file URL under the jsdom environment - jsdom
 * gives the module an http base - so the usual `fileURLToPath(new URL(...))`
 * throws. Vitest runs with its project root as the working directory, which
 * is the frontend package, so resolve from there instead.
 */
import { resolve } from 'node:path'

export const SRC_DIR = resolve(process.cwd(), 'src')

export function fromSrc(...segments: string[]): string {
  return resolve(SRC_DIR, ...segments)
}
