/**
 * Login tokens for tests (ON-38).
 *
 * Real in shape, unsigned in substance: the signature is the literal word
 * "signature". That is not a shortcut — the frontend cannot verify a
 * signature and does not try, because the key is on the server and must
 * stay there (see `session/token.ts`). A test token with a fake signature
 * therefore exercises exactly the code path a real one does.
 *
 * What it must not be is a *valid* token for anything. Nothing here is
 * accepted by the backend, so a token from this file is useless outside
 * the test run.
 */
import type { Role } from '../session/roles'

function base64Url(value: string): string {
  const bytes = new TextEncoder().encode(value)
  const binary = Array.from(bytes, (byte) => String.fromCharCode(byte)).join('')
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

export function makeToken({
  role = 'employee' as Role,
  fullName = 'Ada Employee',
  email = 'employee@onboardai.example',
  userId = 7,
  expiresInMinutes = 720,
  claims = {},
}: {
  role?: Role
  fullName?: string
  email?: string
  userId?: number
  /** Negative for a token that has already run out. */
  expiresInMinutes?: number
  /** Overrides, for testing what happens when a claim is wrong or absent. */
  claims?: Record<string, unknown>
} = {}): string {
  const now = Math.floor(Date.now() / 1000)
  const payload: Record<string, unknown> = {
    sub: String(userId),
    iss: 'onboardai',
    iat: now,
    exp: now + expiresInMinutes * 60,
    email,
    name: fullName,
    role,
    ...claims,
  }
  for (const [key, value] of Object.entries(claims)) {
    // An explicit `undefined` removes the claim, which is how a test asks
    // for a token that is missing one.
    if (value === undefined) delete payload[key]
  }

  const header = base64Url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  return `${header}.${base64Url(JSON.stringify(payload))}.signature`
}

export const EMPLOYEE_TOKEN = makeToken({ role: 'employee', fullName: 'Ada Employee' })

export const HR_TOKEN = makeToken({
  role: 'hr_administrator',
  fullName: 'Hari Administrator',
  email: 'hr@onboardai.example',
  userId: 8,
})
